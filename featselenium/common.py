import ConfigParser
import os
import types

from twisted.trial import unittest

from selenium import webdriver
from selenium.webdriver.remote import webelement
from selenium.webdriver.common import alert

from feat.common import decorator, log, error, reflect, defer, time


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
        if not isinstance(unwrapped, types.MethodType):
            self.logex(5, "%s getattr %s, result: %r:",
                       (self.name, name, unwrapped),
                       depth=-2)
            return unwrapped

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


class SeleniumTest(unittest.TestCase, log.FluLogKeeper, log.Logger):

    def __init__(self, methodName='runTest'):
        log.FluLogKeeper.__init__(self)
        log.Logger.__init__(self, self)
        unittest.TestCase.__init__(self, methodName)

    def run(self, result):
        ini_path = os.environ.get("SELENIUM_INI", '')
        skip_all = None
        if ini_path != 'ignore' and not os.path.exists(ini_path):
            ini_path = os.path.abspath(ini_path)
            skip = (
                "Configuration file not found! You should set the "
                "SELENIUM_INI environment variable. If you really don't "
                "want to use any config set this varialbe to 'ignore'. "
                "The setting at the moment is: %r" % (ini_path, ))
            result.addSkip(self, skip)

        config = Config(ini_path)
        canonical_name = '.'.join([reflect.canonical_name(self),
                                   self._testMethodName])
        os.mkdir(canonical_name)
        backupdir = os.path.abspath(os.path.curdir)
        try:
            os.chdir(os.path.join(os.path.curdir, canonical_name))
            logfile = os.path.join(os.path.curdir, 'test.log')
            log.FluLogKeeper.init(logfile)
            log.FluLogKeeper.redirect_to(None, logfile)
            log.FluLogKeeper.set_debug('5')

            if skip_all:
                result.addSkip(self, skip_all)
            else:
                self.browser = TestDriver(self, suffix='screenshot')
                self.config = config
                unittest.TestCase.run(self, result)

                b = self.browser
                for handle in b.window_handles:
                    b.switch_to_window(handle)
                    self.info(
                        "Grabing screenshot before closing the window "
                        "title: %s", b.title)
                    b.do_screenshot()
                b.quit()
                del(self.browser)
                del(self.config)
        finally:
            os.chdir(backupdir)

        return result

    @defer.inlineCallbacks
    def wait_for(self, check, timeout, freq=0.5, kwargs=dict()):
        try:
            yield time.wait_for(self, check, timeout, freq, kwargs)
        except RuntimeError as e:
            raise unittest.FailTest(str(e))

    def wait_for_windows(self, num, timeout=5):

        def check():
            return len(self.browser.window_handles) == num

        return self.wait_for(check, timeout)


class Config(object):

    def __init__(self, filepath):
        self._cfg = ConfigParser.SafeConfigParser()
        self._cfg.readfp(open(filepath, 'r'))

    def get(self, section, key):
        return self._cfg.get(section, key)


class TestDriver(LogWrapper):
    '''
    Delegates all the method calls selenium.webdriver.Firefox instance.
    Adds login and handles errors.
    '''

    log_category = 'browser'
    wrap_types = (webelement.WebElement, alert.Alert)

    def __init__(self, logkeeper, suffix):
        self._browser = webdriver.Chrome()
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

    def click(browser, xpath, noncritical=False):
        elem = browser.find_element_by_xpath(xpath, noncritical=noncritical)
        if elem:
            elem.click()

    def on_error(self, _e):
        self.do_screenshot()

    ### private ###

    def _screenshot_name(self):
        self._screenshot_counter += 1
        return "%s_%d.png" % (self._suffix, self._screenshot_counter)
