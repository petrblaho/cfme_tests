# These tests don't work at the moment, due to the security_groups multi select not working
# in selenium (the group is selected then immediately reset)
import pytest

from textwrap import dedent

from cfme.automate import explorer as automate
from cfme.cloud.instance import instance_factory
from cfme.cloud.provider import OpenStackProvider
from cfme.fixtures import pytest_selenium as sel
from utils import testgen
from utils.randomness import generate_random_string
from utils.update import update
from utils.wait import wait_for

pytestmark = [pytest.mark.meta(server_roles="+automate")]


def pytest_generate_tests(metafunc):
    # Filter out providers without templates defined
    argnames, argvalues, idlist = testgen.cloud_providers(metafunc, 'provisioning')

    new_argvalues = []
    new_idlist = []
    for i, argvalue_tuple in enumerate(argvalues):
        args = dict(zip(argnames, argvalue_tuple))
        if not args['provisioning']:
            # Don't know what type of instance to provision, move on
            continue

        # required keys should be a subset of the dict keys set
        if not {'image'}.issubset(args['provisioning'].viewkeys()):
            # Need image for image -> instance provisioning
            continue

        if metafunc.function in {
                test_provision_from_template_with_attached_disks, test_provision_with_boot_volume,
                test_provision_with_additional_volume} \
                and args['provider_type'] != 'openstack':
            continue

        new_idlist.append(idlist[i])
        new_argvalues.append([args[argname] for argname in argnames])

    testgen.parametrize(metafunc, argnames, new_argvalues, ids=new_idlist, scope="module")


@pytest.fixture(scope="function")
def vm_name(request, provider_mgmt):
    vm_name = 'test_image_prov_%s' % generate_random_string()
    return vm_name


def test_provision_from_template(request, setup_provider, provider_crud, provisioning, vm_name):
    """ Tests instance provision from template

    Metadata:
        test_flag: provision
    """
    image = provisioning['image']['name']
    note = ('Testing provisioning from image %s to vm %s on provider %s' %
            (image, vm_name, provider_crud.key))

    instance = instance_factory(vm_name, provider_crud, image)

    request.addfinalizer(instance.delete_from_provider)

    inst_args = {
        'email': 'image_provisioner@example.com',
        'first_name': 'Image',
        'last_name': 'Provisioner',
        'notes': note,
        'instance_type': provisioning['instance_type'],
        'availability_zone': provisioning['availability_zone'],
        'security_groups': [provisioning['security_group']],
        'guest_keypair': provisioning['guest_keypair']
    }

    if isinstance(provider_crud, OpenStackProvider):
        inst_args['cloud_network'] = provisioning['cloud_network']

    sel.force_navigate("clouds_instances_by_provider")
    instance.create(**inst_args)


VOLUME_METHOD = ("""
prov = $evm.root["miq_provision"]
prov.set_option(
    :clone_options,
    {:block_device_mapping => [%s]})
""")

ONE_FIELD = """{:volume_id => "%s", :device_name => "%s"}"""


@pytest.fixture(scope="module")
def default_domain_enabled():
    dom = automate.Domain.default
    if dom is not None:
        if not dom.is_enabled:
            with update(dom):
                dom.enabled = True


# Not collected for EC2 in generate_tests above
@pytest.mark.meta(blockers=[1152737])
@pytest.mark.parametrize("disks", [1, 2])
def test_provision_from_template_with_attached_disks(
        request, setup_provider, provider_crud, provisioning, vm_name, provider_mgmt, disks,
        soft_assert, provider_type, default_domain_enabled):
    """ Tests provisioning from a template and attaching disks

    Metadata:
        test_flag: provision
    """

    image = provisioning['image']['name']
    note = ('Testing provisioning from image %s to vm %s on provider %s' %
            (image, vm_name, provider_crud.key))

    DEVICE_NAME = "/dev/sd{}"
    device_mapping = []

    with provider_mgmt.with_volumes(1, n=disks) as volumes:
        for i, volume in enumerate(volumes):
            device_mapping.append((volume, DEVICE_NAME.format(chr(ord("b") + i))))
        # Set up automate
        cls = automate.Class(
            name="Methods",
            namespace=automate.Namespace.make_path("Cloud", "VM", "Provisioning", "StateMachines"))
        method = automate.Method(
            name="openstack_PreProvision",
            cls=cls)
        with update(method):
            disk_mapping = []
            for mapping in device_mapping:
                disk_mapping.append(ONE_FIELD % mapping)
            method.data = VOLUME_METHOD % ", ".join(disk_mapping)

        def _finish_method():
            with update(method):
                method.data = """prov = $evm.root["miq_provision"]"""
        request.addfinalizer(_finish_method)
        instance = instance_factory(vm_name, provider_crud, image)
        request.addfinalizer(instance.delete_from_provider)
        inst_args = {
            'email': 'image_provisioner@example.com',
            'first_name': 'Image',
            'last_name': 'Provisioner',
            'notes': note,
            'instance_type': provisioning['instance_type'],
            'availability_zone': provisioning['availability_zone'],
            'security_groups': [provisioning['security_group']],
            'guest_keypair': provisioning['guest_keypair']
        }

        if isinstance(provider_crud, OpenStackProvider):
            inst_args['cloud_network'] = provisioning['cloud_network']

        sel.force_navigate("clouds_instances_by_provider")
        instance.create(**inst_args)

        for volume_id in volumes:
            soft_assert(vm_name in provider_mgmt.volume_attachments(volume_id))
        for volume, device in device_mapping:
            soft_assert(provider_mgmt.volume_attachments(volume)[vm_name] == device)
        instance.delete_from_provider()  # To make it possible to delete the volume
        wait_for(lambda: not instance.does_vm_exist_on_provider(), num_sec=180, delay=5)


# Not collected for EC2 in generate_tests above
@pytest.mark.meta(blockers=[1160342])
def test_provision_with_boot_volume(
        request, setup_provider, provider_crud, provisioning, vm_name, provider_mgmt, soft_assert,
        provider_type, default_domain_enabled):
    """ Tests provisioning from a template and attaching one booting volume.

    Metadata:
        test_flag: provision, volumes
    """

    image = provisioning['image']['name']
    note = ('Testing provisioning from image %s to vm %s on provider %s' %
            (image, vm_name, provider_crud.key))

    with provider_mgmt.with_volume(1) as volume:
        # Set up automate
        cls = automate.Class(
            name="Methods",
            namespace=automate.Namespace.make_path("Cloud", "VM", "Provisioning", "StateMachines"))
        method = automate.Method(
            name="openstack_CustomizeRequest",
            cls=cls)
        with update(method):
            method.data = dedent('''\
                $evm.root["miq_provision"].set_option(
                    :clone_options, {
                        :image_ref => nil,
                        :block_device_mapping_v2 => [{
                            :boot_index => 0,
                            :uuid => "%s",
                            :device_name => "vda",
                            :source_type => "volume",
                            :destination_type => "volume",
                            :delete_on_termination => false
                        }]
                    }
                )
            ''' % (volume, ))

        def _finish_method():
            with update(method):
                method.data = """prov = $evm.root["miq_provision"]"""
        request.addfinalizer(_finish_method)
        instance = instance_factory(vm_name, provider_crud, image)
        request.addfinalizer(instance.delete_from_provider)
        inst_args = {
            'email': 'image_provisioner@example.com',
            'first_name': 'Image',
            'last_name': 'Provisioner',
            'notes': note,
            'instance_type': provisioning['instance_type'],
            'availability_zone': provisioning['availability_zone'],
            'security_groups': [provisioning['security_group']],
            'guest_keypair': provisioning['guest_keypair']
        }

        if isinstance(provider_crud, OpenStackProvider):
            inst_args['cloud_network'] = provisioning['cloud_network']

        sel.force_navigate("clouds_instances_by_provider")
        instance.create(**inst_args)

        soft_assert(vm_name in provider_mgmt.volume_attachments(volume))
        soft_assert(provider_mgmt.volume_attachments(volume)[vm_name] == "vda")
        instance.delete_from_provider()  # To make it possible to delete the volume
        wait_for(lambda: not instance.does_vm_exist_on_provider(), num_sec=180, delay=5)


# Not collected for EC2 in generate_tests above
@pytest.mark.meta(blockers=[1186413])
def test_provision_with_additional_volume(
        request, setup_provider, provider_crud, provisioning, vm_name, provider_mgmt, soft_assert,
        provider_type, default_domain_enabled, provider_data):
    """ Tests provisioning with setting specific image from AE and then also making it create and
    attach an additional 3G volume.

    Metadata:
        test_flag: provision, volumes
    """

    image = provisioning['image']['name']
    note = ('Testing provisioning from image %s to vm %s on provider %s' %
            (image, vm_name, provider_crud.key))

    # Set up automate
    cls = automate.Class(
        name="Methods",
        namespace=automate.Namespace.make_path("Cloud", "VM", "Provisioning", "StateMachines"))
    method = automate.Method(
        name="openstack_CustomizeRequest",
        cls=cls)
    try:
        image_id = provider_mgmt.get_template_id(provider_data["small_template"])
    except KeyError:
        pytest.skip("No small_template in provider adta!")
    with update(method):
        method.data = dedent('''\
            $evm.root["miq_provision"].set_option(
              :clone_options, {
                :image_ref => nil,
                :block_device_mapping_v2 => [{
                  :boot_index => 0,
                  :uuid => "%s",
                  :device_name => "vda",
                  :source_type => "image",
                  :destination_type => "volume",
                  :volume_size => 3,
                  :delete_on_termination => false
                }]
              }
        )
        ''' % (image_id, ))

    def _finish_method():
        with update(method):
            method.data = """prov = $evm.root["miq_provision"]"""
    request.addfinalizer(_finish_method)
    instance = instance_factory(vm_name, provider_crud, image)
    request.addfinalizer(instance.delete_from_provider)
    inst_args = {
        'email': 'image_provisioner@example.com',
        'first_name': 'Image',
        'last_name': 'Provisioner',
        'notes': note,
        'instance_type': provisioning['instance_type'],
        'availability_zone': provisioning['availability_zone'],
        'security_groups': [provisioning['security_group']],
        'guest_keypair': provisioning['guest_keypair']
    }

    if isinstance(provider_crud, OpenStackProvider):
        inst_args['cloud_network'] = provisioning['cloud_network']

    sel.force_navigate("clouds_instances_by_provider")
    instance.create(**inst_args)

    prov_instance = provider_mgmt._find_instance_by_name(vm_name)
    try:
        assert hasattr(prov_instance, 'os-extended-volumes:volumes_attached')
        volumes_attached = getattr(prov_instance, 'os-extended-volumes:volumes_attached')
        assert len(volumes_attached) == 1
        volume_id = volumes_attached[0]["id"]
        assert provider_mgmt.volume_exists(volume_id)
        volume = provider_mgmt.get_volume(volume_id)
        assert volume.size == 3
    finally:
        instance.delete_from_provider()
        wait_for(lambda: not instance.does_vm_exist_on_provider(), num_sec=180, delay=5)
        if volume_id in locals():
            if provider_mgmt.volume_exists(volume_id):
                provider_mgmt.delete_volume(volume_id)
