"""A set of functions for dealing with accordions in the UI.

Usage:

    Using Accordions is simply a case of either selecting it to return the element,
    or using the built in click method. As shown below::

      acc = web_ui.accordion

      acc.click('Diagnostics')
      acc.is_active('Diagnostics')

Note:
    Inactive links are not available in any way.
"""
from xml.sax.saxutils import quoteattr


import cfme.fixtures.pytest_selenium as sel
from cfme.exceptions import ListAccordionLinkNotFound
from utils.pretty import Pretty

LOCATOR = "|".join([
    # The older one
    '//div[contains(@class, "dhx_acc_item") or @class="topbar"]'
    '/*[contains(@data-remote, "true") and normalize-space(.)={accname}]',
    # The newer one
    "//div[contains(@class, 'panel-group')]/div[contains(@class, 'panel-')]/div/h4"
    "/a[@data-toggle and normalize-space(.)={accname}]"
])


def locate(name):
    """ Returns a list-accordion by name

    Args:
        name: The name of the accordion.
    Returns: An xpath locator of the selected accordion.
    """
    return LOCATOR.format(accname=quoteattr(name))


def click(name):
    """ Clicks an accordion and returns it

    Args:
        name: The name of the accordion.
    """
    xpath = locate(name)
    el = sel.element(xpath)
    was_active = is_active(name)
    sel.click(el)
    if not was_active:
        # sel.wait_for_element(cls._content_element(name))
        # This is ugly but the above doesn't work
        import time
        time.sleep(3)


def _content_element(name):
    """ Element with content of section specified by name

    Args:
        name: The name of the accordion.
    """
    root = sel.element(locate(name))
    # Older or newer locator
    el = sel.element('./../following-sibling::div[1]|'
                     './../../following-sibling::div//ul[contains(@class, "nav-stack")]', root=root)
    return el


def is_active(name):
    """ Checks if an accordion is currently open

    Args:
        name: The name of the accordion.
    Returns: ``True`` if the button is depressed, ``False`` if not.
    """
    return sel.is_displayed(_content_element(name))


def select(name, link_title):
    """ Clicks an active link in accordion section

    Args:
        name: Name of the accordion.
        link_title: Title of link in expanded accordion section.
    """
    if not is_active(name):
        click(name)
    link_root = _content_element(name)
    link = ListAccordionLink(link_title, link_root)
    link.click()


def get_active_links(name):
    """ Returns all active links in a section specified by name

    Args:
        name: Name of the section
    """
    link_root = _content_element(name)
    link_loc = './/div[@class="panecontent"]//a[@title and not(child::img)]|'\
               './li[not(contains(@class, "disabled"))]/a'
    active_els = sel.elements(link_loc, root=link_root)
    return [ListAccordionLink(el.get_attribute("title"), link_root) for el in active_els]


class ListAccordionLink(Pretty):
    """ Active link in an accordion section

    Args:
        title: The title of the link.
    """
    pretty_attrs = ['title', 'root']

    def __init__(self, title, root=None):
        self.root = root
        self.title = title

    def locate(self):
        """ Locates an active link.

        Returns: An XPATH locator for the element."""
        locator = './/div[@class="panecontent"]//a[@title="{title}" and not(child::img)]|'\
                  './li[not(contains(@class, "disabled"))]/a[@title="{title}"]'\
                  .format(title=self.title)
        return locator

    def _check_exists(self):
        try:
            sel.element(self.locate(), root=self.root)
        except sel.NoSuchElementException:
            raise ListAccordionLinkNotFound(
                'No active link with title "{}" found.'.format(self.title))

    def click(self):
        """ Clicks a link by title.

        Args:
            title: The title of the button to check.

        Raises:
            ListAccordionLinkNotFound: when active link is not found.
        """
        self._check_exists()
        sel.click(sel.element(self.locate(), root=self.root))
