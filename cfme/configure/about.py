# -*- coding: utf-8 -*-
from cfme.web_ui import Region
from utils import version

product_assistance = Region(
    locators={
        'quick_start_guide': "//a[normalize-space(.)='Quick Start Guide']",
        'insight_guide': "//a[normalize-space(.)='Insight Guide']",
        'control_guide': "//a[normalize-space(.)='Control Guide']",
        'lifecycle_and_automation_guide':
        "//a[normalize-space(.)='Lifecycle and Automation Guide']",
        'integrate_guide': {
            version.LOWEST: "//a[normalize-space(.)='Integrate Guide']",
            '5.3': "//a[normalize-space(.)='Integration Services Guide']"
        },
        'settings_and_operations_guide': "//a[normalize-space(.)='Settings and Operations Guide']",
        'red_hat_customer_portal': "//a[normalize-space(.)='Red Hat Customer Portal']"
    },
    title='About',
    identifying_loc='quick_start_guide',
    infoblock_type="form"
)
