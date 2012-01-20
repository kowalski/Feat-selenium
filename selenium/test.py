from selenium import webdriver
from selenium.webdriver.remote import webelement
# from selenium.webdriver.common.keys import Keys

from feat.common import decorator, log, error
import time


class LogWrapper(log.Logger):
    '''
    Delegates all method calls to what it wraps around.
    Adds logging about each method calls.
    '''

    wrap_types = tuple()

    def __init__(self, logkeeper, delegate):
        log.Logger.__init__(self, logkeeper)
        self._delegate = delegate

    @property
    def name(self):
        return type(self._delegate).__name__

    def __getattr__(self, name):
        # forward all other access to the browser object
        # decorate the methods to add logging
        unwrapped = getattr(self._delegate, name)

        def wrapped(*args, **kwargs):
            noncritical = kwargs.pop('noncritical', False)
            self.logex(5, "%s call: %s, args=%r, kwargs=%r",
                       (self.name, unwrapped.__name__, args, kwargs),
                       depth=-3)
            try:
                res = unwrapped(*args, **kwargs)
                if isinstance(res, self.wrap_types):
                    res = LogWrapper(self._logger, res)
                return res
            except Exception as e:
                error.handle_exception(
                    self, e,
                    "%s call failed, name: %s, args=%r, kwargs=%r",
                    self.name, unwrapped.__name__, args, kwargs)
                self.on_error(e)
                if not noncritical:
                    raise
                else:
                    self.info("Test will continue, as the call was done "
                              "with noncritical=True")

        decorator._function_mimicry(unwrapped, wrapped)
        return wrapped

    def on_error(self, e):
        '''override in subclasses'''
        pass


class TestDriver(LogWrapper):
    '''
    Delegates all the method calls selenium.webdriver.Firefox instance.
    Adds login and handles errors.
    '''

    log_category = 'browser'
    wrap_types = (webelement.WebElement, )

    def __init__(self, logkeeper, suffix):
        self._browser = webdriver.Firefox()
        LogWrapper.__init__(self, logkeeper, self._browser)
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

    def on_error(self, _e):
        self.do_screenshot()

    ### private ###

    def _screenshot_name(self):
        self._screenshot_counter += 1
        return "%s_%d.png" % (self._suffix, self._screenshot_counter)


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
