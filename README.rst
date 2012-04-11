This is an integration layer between trial and selenium driver.

Setup
-----

I use this repository as a submodule of the project in which I keep the selenium tests.

Clone it like this:

git submodule add git@github.com:kowalski/Feat-selenium.git
ln -s Feat-selenium/featselenium .

To use it you also need feat (https://github.com/f3at/feat) in the PYTHONPATH.

Running tests
-------------

To run the tests you need to:

1. Have chromedriver in your PATH, for example: ::

  ln -s Feat-selenium/vendor/chromedriver ~/bin

2. Run selenium-server: ::

  java -jar Feat-selenium/vendor/selenium-server-standalone-2.20.0.jar

3. Say which config you want to use, for example for .local domain use: ::

  export SELENIUM_INI=`pwd`/local.ini

The config is just an .ini file which will be parsed with ConfigParser and available in your tests under self.config refererence.

4. You are good to go, run tests with: ::

  trial moduleinwhichyoukeepselenium


(all the commands assume that you are in root of the repository)


Debugging
---------

Each test of the testsuite creates a directory *_trial_temp/<canonical_name>*. Under this path you would find the *test.log* file and all the screenshots taken during the test.

