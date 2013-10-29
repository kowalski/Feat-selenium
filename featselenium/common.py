import base64
import ConfigParser
import os
import types
import sys

from twisted.trial import unittest
from twisted.python import failure
from twisted.internet import threads

from poster import encode

from selenium import webdriver
from selenium.webdriver.remote import webelement
from selenium.webdriver.remote.command import Command
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.common import alert
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.common import exceptions

from feat.common import decorator, log, error, reflect, defer, time
from feat.web import http, httpclient


def explicitly_wait(method, args=tuple(), kwargs=dict(), poll=0.5, timeout=10):
    end_time = time.time() + timeout
    while(True):
        try:
            return method(*args, **kwargs)
        except (exceptions.NoSuchElementException,
                exceptions.StaleElementReferenceException,
                exceptions.InvalidSelectiorException):
            if(time.time() > end_time):
                raise
        time.sleep(poll)


class LogWrapper(log.Logger):
    '''
    Delegates all method calls to what it wraps around.
    Adds logging about each method calls.
    '''

    wrap_types = tuple()

    def __init__(self, logkeeper, delegate, work_in_thread=False):
        log.Logger.__init__(self, logkeeper)
        self._delegate = delegate
        self.set_explicit_wait(None)
        self._work_in_thread = work_in_thread

    def set_explicit_wait(self, timeout):
        self._explicit_wait = timeout

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
                if self._explicit_wait is None:
                    return self._wrap_call(unwrapped, *args, **kwargs)
                else:
                    return self._wrap_call(explicitly_wait,
                                           unwrapped, args, kwargs,
                                           timeout=self._explicit_wait)
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

    def _wrap_call(self, __method, *args, **kwargs):
        if not self._work_in_thread:
            res = __method(*args, **kwargs)
            return self._wrap_call_result(res)
        else:
            d = threads.deferToThread(__method, *args, **kwargs)
            d.addCallback(self._wrap_call_result)
            return d

    def _wrap_call_result(self, res):
        if isinstance(res, self.wrap_types):
            res = LogWrapper(self._logger, res,
                             work_in_thread=self._work_in_thread)
        return res

    def on_error(self, e):
        '''override in subclasses'''
        pass


class SeleniumTest(unittest.TestCase, log.FluLogKeeper, log.Logger):

    artifact_counters = dict()
    threaded_selenium = False

    def __init__(self, methodName='runTest'):
        log.FluLogKeeper.__init__(self)
        log.set_default(self)
        log.Logger.__init__(self, self)
        unittest.TestCase.__init__(self, methodName)

    @property
    def config(self):
        if not hasattr(self, '_selenium_config'):
            ini_path = os.environ.get("SELENIUM_INI", '')
            ini_path = os.path.abspath(ini_path)
            try:
                self._selenium_config = Config(ini_path)
            except Exception:
                msg = (
                    "Configuration file not found! You should set the "
                    "SELENIUM_INI environment variable to point to existing "
                    "file. The setting at the moment is: %r" % (ini_path, ))
                raise self.failureException(msg), None, sys.exc_info()[2]
        return self._selenium_config

    def run(self, result):
        backupdir = os.path.abspath(os.path.curdir)
        try:
            canonical_name = '.'.join([reflect.canonical_name(self),
                                       self._testMethodName])
            testcase_dir = os.path.join(os.path.curdir, canonical_name)
            os.mkdir(testcase_dir)
            os.chdir(testcase_dir)

            logfile = os.path.join(os.path.curdir, 'test.log')
            log.FluLogKeeper.init(logfile)
            log.FluLogKeeper.redirect_to(None, logfile)
            log.FluLogKeeper.set_debug('5')

            self.browser = TestDriver(self, suffix='screenshot',
                                      work_in_thread=self.threaded_selenium)
            unittest.TestCase.run(self, result)

            b = self.browser
            # when the test is finished reactor might not be running,
            # we need to force switching browser to synchronous mode
            b._work_in_thread = False
            for handle in b.window_handles:
                b.switch_to_window(handle)
                self.info(
                    "Grabbing screenshot before closing the window "
                    "title: %s", b.title)
                b.do_screenshot()
            b.quit()
            del(self.browser)
        except Exception:
            result.addError(self, failure.Failure())
        finally:
            os.chdir(backupdir)

        return result

    @defer.inlineCallbacks
    def wait_for(self, check, timeout, freq=0.5, kwargs=dict()):
        try:
            yield time.wait_for_ex(check, timeout, freq, kwargs=kwargs,
                                   logger=self)
        except RuntimeError as e:
            raise unittest.FailTest(str(e))

    def wait_for_windows(self, num, timeout=5):

        def check():
            return len(self.browser.window_handles) == num

        return self.wait_for(check, timeout)

    def wait_for_ajax(self, timeout=30):

        @defer.inlineCallbacks
        def check():
            active = yield self.browser.get_active_ajax()
            defer.returnValue(active == 0)

        return self.wait_for(check, timeout)

    @defer.inlineCallbacks
    def wait_for_alert(self, timeout=10):

        def check():
            try:
                alert = self.browser.switch_to_alert()
                alert.text
                return True
            except exceptions.NoAlertPresentException:
                return False

        yield self.wait_for(check, timeout)

        defer.returnValue(self.browser.switch_to_alert())

    @defer.inlineCallbacks
    def validate_html(self):
        try:
            if os.environ['SELENIUM_SKIP_HTML_VALIDATION']:
                return
        except KeyError:
            pass
        url = os.environ.get("SELENIUM_VALIDATOR", 'validator.w3.org')
        validator = httpclient.Connection(url, 80, logger=self)
        self.addCleanup(validator.disconnect)

        source = self.browser.page_source
        # browser returns the result as ISO-8859-1 encoded, but it's later
        # interpreted as unicode. Here I just remove all the nonascii
        # characters from the input, I didn't find the better way to deal
        # with this.
        source = "".join(x for x in source if ord(x) < 128)

        datagen, headers = encode.multipart_encode({
            'fragment': source,
            'charset': '(detect automatically)',
            'group': 0,
            'ss': 1,
            'user-agent': 'W3C_Validator/1.3',
            'doctype': 'inline'})
        body = "".join(datagen)
        # HttpConnection for some reason uses lowercase headers
        headers = dict((k.lower(), v) for k, v in headers.iteritems())

        self.info("Validating html. Posting to %s/check", validator._host)

        try:
            response = yield validator.request(
                http.Methods.POST, '/check', headers, body)
        except Exception as e:
            error.handle_exception(self, e, "Failed posting to validator")
            self.fail("Failed posting to validator")
        errors = response.headers.get('x-w3c-validator-errors')

        if errors != '0':
            html_name = '%s.html' % (self.browser.title, )
            with open(html_name, 'w') as f:
                f.write(response.body)
            self.fail("Failing because of invalid html. "
                      "Saved validator output to %s\n" % (html_name, ))

    def archive_screenshot(self, name, prefix):
        target = os.environ.get('SELENIUM_ARTIFACTS')
        if target is None:
            self.info("Not making screenshots because SELENIUM_ARTIFACTS "
                      "enviroment variable is not set.")
            return
        if not os.path.isdir(target):
            self.fail("SELENIUM_ARTIFACTS environment variable should "
                      "be set to an existing directory path, not %r" %
                      (target, ))
        counter = type(self).artifact_counters.get(prefix, 0)
        counter += 1
        type(self).artifact_counters[prefix] = counter
        name = "%s_%02d_%s.png" % (prefix, counter, name)
        path = os.path.join(target, name)
        self.info("Archiving a screenshot to: %r", path)
        return self.browser.get_screenshot_as_file(path)


class Config(object):

    def __init__(self, filepath):
        self._cfg = ConfigParser.SafeConfigParser()
        self._cfg.readfp(open(filepath, 'r'))

    def get(self, section, key):
        return self._cfg.get(section, key)


class RemoteIE(RemoteWebDriver):

    def __init__(self, host, port):
        executor = 'http://%s:%d/wd/hub' % (host, port)
        RemoteWebDriver.__init__(
            self, command_executor=executor,
            desired_capabilities=DesiredCapabilities.INTERNETEXPLORER)

    def save_screenshot(self, filename):
        """
        Gets the screenshot of the current window. Returns False if there is
        any IOError, else returns True. Use full paths in your filename.
        """
        png = RemoteWebDriver.execute(self, Command.SCREENSHOT)['value']
        try:
            f = open(filename, 'wb')
            f.write(base64.decodestring(png))
            f.close()
        except IOError:
            return False
        finally:
            del png
        return True


class TestDriver(LogWrapper):
    '''
    Delegates all the method calls selenium.webdriver.Firefox instance.
    Adds login and handles errors.
    '''

    log_category = 'browser'
    wrap_types = (webelement.WebElement, alert.Alert)

    def __init__(self, logkeeper, suffix, work_in_thread=False):
        brow = os.environ.get('SELENIUM_BROWSER', '').upper()
        if brow == 'FIREFOX':
            binary = None
            path = os.environ.get('SELENIUM_FIREFOX', '')
            if path:
                binary = FirefoxBinary(path)
            self._browser = webdriver.Firefox(firefox_binary=binary)
            self.browser = 'Firefox'
        elif brow == "MSIE":
            remote = os.environ.get("SELENIUM_REMOTE_IE")
            if not remote:
                raise ValueError("For MSIE type of driver you need to set"
                                 " the SELENIUM_REMOTE_IE variable with the "
                                 "address to send commands to.")
            host, port = remote.split(":")
            port = int(port)
            self._browser = RemoteIE(host, port)
            self.browser = 'MSIE'
        else:
            from selenium.webdriver.chrome import options
            chrome_options = options.Options()
            chrome_options.add_argument("--disable-extensions")
            self._browser = webdriver.Chrome(chrome_options=chrome_options)
            self.browser = 'Chrome'
        LogWrapper.__init__(self, logkeeper, self._browser,
                            work_in_thread=work_in_thread)
        self.debug('Browser %s', self.browser)
        if self.msie:
            self.set_explicit_wait(10)
        self._suffix = suffix
        self._screenshot_counter = 0

    @property
    def msie(self):
        return self.browser == "MSIE"

    def do_screenshot(self):
        filename = self._screenshot_name()
        self.info("Saving screenshot to: %s", filename)
        return self._browser.get_screenshot_as_file(filename)

    def input_field(browser, xpath, value, noncritical=False):
        if browser.msie:

            def set_value(browser, xpath, value):
                elem = browser.find_element_by_xpath(xpath)
                browser.execute_script(
                    'arguments[0].value = "%s"' % (value, ), elem)

            explicitly_wait(set_value, args=(browser._delegate, xpath, value))
        else:
            elem = browser.find_element_by_xpath(xpath,
                                                 noncritical=noncritical)
            if not isinstance(elem, defer.Deferred):
                elem.clear()
                elem.send_keys(value)
            else:
                elem.addCallback(defer.keep_param, defer.call_param, 'clear')
                elem.addCallback(defer.call_param, 'send_keys', value)
                return elem

    def click(browser, elem, noncritical=False):
        if isinstance(elem, (str, unicode)):
            # xpath was passed
            elem = browser.find_element_by_xpath(elem, noncritical=noncritical)
        elif not isinstance(elem, LogWrapper):
            raise TypeError('argument 2 of click() should be an xpath or '
                            'element, %r passed' % (elem, ))
        if isinstance(elem, defer.Deferred):
            elem.addCallback(defer.call_param, 'click')
            return elem
        elif elem:
            if browser.msie:
                # in IE calling clicking inputs inside the iframe
                # has no effect
                # http://code.google.com/p/selenium/issues/detail?id=2387
                browser.execute_script("arguments[0].click()", elem._delegate)
            else:
                return elem.click()

    def on_error(self, _e):
        self.do_screenshot()

    def script_result(browser, script):
        browser.execute_script(
            "$('body').append('<div id=\"js-result\"></div>');"
            "$('#js-result').html(%s);" % (script, ))
        el = browser.find_element_by_xpath('//div[@id="js-result"]')
        res = el.text
        browser.execute_script("$('div#js-result').remove()")
        return res

    def get_active_ajax(browser):
        r = browser.execute_script("return $.active")
        if isinstance(r, defer.Deferred):
            r.addCallback(int)
            return r
        else:
            return int(r)

    ### private ###

    def _screenshot_name(self):
        self._screenshot_counter += 1
        return "%s_%d.png" % (self._suffix, self._screenshot_counter)
