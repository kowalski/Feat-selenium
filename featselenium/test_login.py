import sys

from featselenium import common


class LoginTest(common.SeleniumTest):

    def testLogin(self):
        browser = self.browser
        browser.get(self.config.get('login', 'url'))

        browser.input_field('//*[@id="id_username"]',
                            self.config.get('login', 'username'))
        browser.input_field('//*[@id="id_password"]',
                            self.config.get('login', 'password'))

        submit = browser.find_element_by_xpath(
            '*//form[@class="genericForm"]//input[@type="submit"]')
        submit.click()

test_suite = common.SeleniumTestSuiteFactory(sys.modules[__name__])
