This is an integration layer between trial and selenium driver. Its capable of running tests against Chrome, Firefox and Internet Explorer. It offers tools for validating HTML against the remote service (w3c.validator.org) and gathering screenshot artifacts from the run.

Setup
-----

I use this repository as a submodule of the project in which I keep the selenium tests.

Clone it like this: ::

  git submodule add git@github.com:kowalski/Feat-selenium.git
  ln -s Feat-selenium/featselenium .

To use it you also need feat (https://github.com/f3at/feat) in the PYTHONPATH.

Running tests
-------------

To run the tests you need to:

  1. Choose and configure the browser (see next section).

  2. Say which config you want to use, for example for .local domain use: ::

       export SELENIUM_INI=`pwd`/local.ini

The config is just an .ini file which will be parsed with ConfigParser and available in your tests under self.config refererence.

  3. You are good to go, run tests with: ::

       trial moduleinwhichyoukeepselenium


(all the commands assume that you are in root of the repository)


Browsers supported
------------------

I'm running my tests against the newest version of Chrome and old Firefox (3.6.8). Unfortunately the new versions of FF are just dying unexpectedly.. maybe they will fix it someday.

The default is to run tests against Chrome. It requires no further configuration.

Firefox
=======

To use firefox set the following variable: ::

  export SELENIUM_BROWSER=firefox

To use the older version of firefox than currently installed on the system use ::

  export SELENIUM_FIREFOX=/path/to/custom/firefox

In case you need to do something browser-specific in your test you can always check which browser is running by looking at *self.browser.browser* attribute which will be either 'Chrome', 'Firefox' or 'MSIE'.


Internet explorer
=================

The setup of the test with Internet Explorer is somewhat different, because it runs on the remote machine. Set the following variables: ::

  export SELENIUM_BROWSER=MSIE
  export SELENIUM_REMOTE_IE=ip:port

The above is the address of the server the selenium grid launcher is running on. Default port it uses is 4444.

===========================
Setup of the remote machine
===========================

Before you can start the test you need to setup the remote machine as well. Go to selenium download page (http://code.google.com/p/selenium/downloads/list) and download the latest *selenium-server-standalone-VERSION.jar* and *IEDriverServer_ARCH_VERSION.zip*. Now to run the selenium grid use: ::

  java -Dwebdriver.ie.driver="PATH_TO/IEDriverServer.exe" -jar selenium-server-standalone-VERSION.jar

Hint: if you are using virtual box to run windows you should configure the network adapter to "Bridge network adapters" option, so that the virtual machine is on the same network as the host.


Debugging
---------

Each test of the testsuite creates a directory *_trial_temp/<canonical_name>*. Under this path you would find the *test.log* file and all the screenshots taken during the test.


Validating HTML
---------------

From anyware in your test case you can call: ::

   yield self.validate_html()

To validate the current page html against the external service. Note that this method returns a Deferred which should be yielded. By default the validation service used is: *validator.w3.org*. If you host this tool in your local subnet, you can override this setting by: ::

   export SELENIUM_VALIDATOR="validator.local.net"

If you want to skip the validation for the run use: ::

   export SELENIUM_SKIP_HTML_VALIDATION=1


Gathering artifacts
-------------------

Run of selenium tests can leave behind the set of screenshots which can be archived somewhere. To tell the test suite to archive a screenshot use the following code: ::

   self.archive_screenshot(name, prefix='PREFIX')

This will create a screenshot with the name PREFIX_COUNTER_NAME.png.

To enable this tools set the following variable: ::

  export SELENIUM_ARTIFACTS="/path/to/target"

Please note that this variable has to point to an exisiting directory.


