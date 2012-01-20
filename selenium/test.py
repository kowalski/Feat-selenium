import uuid

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
# from selenium.webdriver.common.keys import Keys

from feat.common import decorator, log, error
import time


class TestDriver(log.Logger):
    '''
    Delegates all the method calls selenium.webdriver.Firefox instance.
    Adds login and handles errors.
    '''

    log_category = 'browser'

    def __init__(self, logkeeper, suffix):
        log.Logger.__init__(self, logkeeper)
        self._browser = webdriver.Firefox()
        self._suffix = suffix
        self._screenshot_counter = 0

    def do_screenshot(self):
        filename = self._screenshot_name()
        self.info("Saving screenshot to: %s", filename)
        self._browser.get_screenshot_as_file(filename)

    def input_field(browser, xpath, value, noncritical=False):
        elem = browser.find_element_by_xpath(xpath, noncritical=noncritical)
        if elem:
            elem.send_keys(value)

    ### private ###

    def _screenshot_name(self):
        self._screenshot_counter += 1
        return "%s_%d.png" % (self._suffix, self._screenshot_counter)

    def __getattr__(self, name):
        # forward all other access to the browser object
        # decorate the methods to add logging
        unwrapped = getattr(self._browser, name)

        def wrapped(*args, **kwargs):
            noncritical = kwargs.pop('noncritical', False)
            self.logex(5, "Browser call: %s, args=%r, kwargs=%r",
                       (unwrapped.__name__, args, kwargs),
                       depth=-3)
            try:
                res = unwrapped(*args, **kwargs)
                print type(res)
                return res
            except Exception as e:
                error.handle_exception(
                    self, e,
                    "Browser call failed, name: %s, args=%r, kwargs=%r",
                    unwrapped.__name__, args, kwargs)
                self.do_screenshot()
                if not noncritical:
                    raise
                else:
                    self.info("Test will continue, as the call was done "
                              "with noncritical=True")

        decorator._function_mimicry(unwrapped, wrapped)
        return wrapped



URL = "https://web1.flt.fluendo.lan/accounts/login/"
USERNAME = "devteam@flumotion.com"
PASSWORD = "meis5iNg"


if __name__ == '__main__':
    log.FluLogKeeper.init()
    log.FluLogKeeper.set_debug('5')
    keeper = log.FluLogKeeper()
    try:
        browser = TestDriver(keeper, suffix='login')
        browser.get(URL)

        browser.input_field('//*[@id="id_username"]', USERNAME)
        browser.input_field('//*[@id="id_password"]', PASSWORD)
        submit = browser.find_element_by_xpath(
            '*//form[@class="genericForm"]//input[@type="submit"]')
        submit.click()

    finally:
        browser.do_screenshot()
        time.sleep(10)
        browser.close()
