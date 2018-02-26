import json
import os
import socket
import sys
import threading
import time
import traceback
import urlparse
import uuid

from .base import (Protocol,
                   RefTestExecutor,
                   RefTestImplementation,
                   TestharnessExecutor,
                   WebDriverProtocol,
                   extra_timeout,
                   strip_server)
from ..testrunner import Stop

here = os.path.join(os.path.split(__file__)[0])

webdriver = None
exceptions = None
RemoteConnection = None


def do_delayed_imports():
    global webdriver
    global exceptions
    global RemoteConnection
    from selenium import webdriver
    from selenium.common import exceptions
    from selenium.webdriver.remote.remote_connection import RemoteConnection

class WebDriverRun(object):
    def __init__(self, func, session, url, timeout):
        self.func = func
        self.result = None
        self.session = session
        self.url = url
        self.timeout = timeout
        print(timeout)
        self.result_flag = threading.Event()

    def run(self):
        timeout = self.timeout

        # try:
        #     self.webdriver.set_script_timeout((timeout + extra_timeout) * 1000)
        # except exceptions.ErrorInResponseException:
        #     self.logger.error("Lost WebDriver connection")
        #     return Stop

        executor = threading.Thread(target=self._run)
        executor.start()

        flag = self.result_flag.wait(timeout + 2 * extra_timeout)
        if self.result[1] is None:
            # assert not flag
            self.result = False, ("EXTERNAL-TIMEOUT", None)

        return self.result

    def _run(self):
        try:
            self.result = True, self.func(self.session, self.url, self.timeout)
        except (socket.timeout, IOError):
            self.result = False, ("CRASH", None)
        except Exception as e:
            message = getattr(e, "message")
            if message:
                message += "\n"
            message += traceback.format_exc(e)
            self.result = False, ("ERROR", message)
        finally:
            self.result_flag.set()

    # def _run(self):
    #     try:
    #         self.result = True, self.func(self.session, self.url, self.timeout)
    #     except exceptions.TimeoutException:
    #         self.result = False, ("EXTERNAL-TIMEOUT", None)
    #     except (socket.timeout, exceptions.ErrorInResponseException):
    #         self.result = False, ("CRASH", None)
    #     except Exception as e:
    #         message = getattr(e, "message", "")
    #         if message:
    #             message += "\n"
    #         message += traceback.format_exc(e)
    #         self.result = False, ("ERROR", e)
    #     finally:
    #         self.result_flag.set()


class WebDriverTestharnessExecutor(TestharnessExecutor):
    supports_testdriver = True
    protocol_cls = None

    def __init__(self, browser, server_config, timeout_multiplier=1,
                 close_after_done=True, capabilities=None, debug_info=None,
                 **kwargs):
        """WebDriver-based executor for testharness.js tests"""
        TestharnessExecutor.__init__(self, browser, server_config,
                                     timeout_multiplier=timeout_multiplier,
                                     debug_info=debug_info)
        self.capabilities = capabilities
        self.webdriver_binary = browser.webdriver_binary
        self.webdriver_args = browser.webdriver_args
        self.protocol = self.protocol_cls(self, browser)
        with open(os.path.join(here, "testharness_webdriver.js")) as f:
            self.script = f.read()
        with open(os.path.join(here, "testharness_webdriver_resume.js")) as f:
            self.script_resume = f.read()
        self.close_after_done = close_after_done
        self.window_id = str(uuid.uuid4())

    def is_alive(self):
        return self.protocol.is_alive()

    def on_environment_change(self, new_environment):
        if new_environment["protocol"] != self.last_environment["protocol"]:
            self.protocol.load_runner(new_environment["protocol"])

    def do_test(self, test):
        timeout = test.timeout * self.timeout_multiplier + extra_timeout
        url = self.test_url(test)

        success, data = WebDriverRun(self.do_testharness,
                                    self.protocol.session,
                                    url,
                                    test.timeout * self.timeout_multiplier).run()

        if success:
            return self.convert_result(test, data)

        return (test.result_cls(*data), [])

    def do_testharness(self, session, url, timeout):
        format_map = {"abs_url": url,
                      "url": strip_server(url),
                      "window_id": self.window_id,
                      "timeout_multiplier": self.timeout_multiplier,
                      "timeout": timeout * 1000}

        parent = session.send_session_command('GET', 'window')
        window_handles = session.send_session_command('GET', 'window/handles')
        handles = [item for item in window_handles if item != parent]
        for handle in handles:
            try:
                session.send_session_command('POST', 'window', {'handle': handle})
                session.send_session_command('DELETE', 'window')
            except exceptions.NoSuchWindowException:
                pass
        session.send_session_command('POST', 'window', {'handle': parent})

        session.send_session_command('POST', 'execute/sync', {'script': self.script % format_map, 'args': []})
        try:
            # Try this, it's in Level 1 but nothing supports it yet
            session.send_session_command('POST', 'execute/sync', {'script': "return window['%s'];" % self.window_id, 'args': []})
            win_obj = json.loads(win_s)
            test_window = win_obj["window-fcc6-11e5-b4f8-330a88ab9d7f"]
        except Exception:
            after = window_handles = session.send_session_command('GET', 'window/handles')
            if len(after) == 2:
                test_window = next(iter(set(after) - set([parent])))
            elif after[0] == parent and len(after) > 2:
                # Hope the first one here is the test window
                test_window = after[1]
            else:
                raise Exception("unable to find test window")
        assert test_window != parent

        handler = CallbackHandler(session, test_window, self.logger)
        while True:
            result = session.send_session_command('POST', 'execute/async', {'script': self.script_resume % format_map, 'args': []})
            done, rv = handler(result)
            if done:
                break
        return rv


class CallbackHandler(object):
    def __init__(self, session, test_window, logger):
        self.session = session
        self.test_window = test_window
        self.logger = logger

    def __call__(self, result):
        self.logger.debug("Got async callback: %s" % result[1])
        try:
            attr = getattr(self, "process_%s" % result[1])
        except AttributeError:
            raise ValueError("Unknown callback type %r" % result[1])
        else:
            return attr(result)

    def process_complete(self, result):
        rv = [result[0]] + result[2]
        return True, rv

    def process_action(self, result):
        parent = session.send_session_command('GET', 'window')
        try:
            session.send_session_command('POST', 'window', {'handle': self.test_window})
            # self.webdriver.switch_to.window(self.test_window)
            action = result[2]["action"]
            self.logger.debug("Got action: %s" % action)
            if action == "click":
                selector = result[2]["selector"]
                #TODO: THIS
                elements = self.webdriver.find_elements_by_css_selector(selector)
                if len(elements) == 0:
                    raise ValueError("Selector matches no elements")
                elif len(elements) > 1:
                    raise ValueError("Selector matches multiple elements")
                self.logger.debug("Clicking element: %s" % selector)
                try:
                    elements[0].click()
                except (exceptions.ElementNotInteractableException,
                        exceptions.ElementNotVisibleException) as e:
                    self._send_message("complete",
                                       "failure",
                                       e)
                    self.logger.debug("Clicking element failed: %s" % str(e))
                else:
                    self._send_message("complete",
                                       "success")
                    self.logger.debug("Clicking element succeeded")
        finally:
            session.send_session_command('POST', 'window', {'handle': parent})

        return False, None

    def _send_message(self, message_type, status, message=None):
        obj = {
            "type": "testdriver-%s" % str(message_type),
            "status": str(status)
        }
        if message:
            obj["message"] = str(message)

        session.send_session_command('POST', 'execute/sync', {'script': "window.postMessage(%s, '*')" % json.dumps(obj), 'args': []})



class WebDriverRefTestExecutor(RefTestExecutor):
    def __init__(self, browser, server_config, timeout_multiplier=1,
                 screenshot_cache=None, close_after_done=True,
                 debug_info=None, capabilities=None, **kwargs):
        """Selenium WebDriver-based executor for reftests"""
        RefTestExecutor.__init__(self,
                                 browser,
                                 server_config,
                                 screenshot_cache=screenshot_cache,
                                 timeout_multiplier=timeout_multiplier,
                                 debug_info=debug_info)
        self.protocol = WebDriverProtocol(self, browser,
                                         capabilities=capabilities)
        self.implementation = RefTestImplementation(self)
        self.close_after_done = close_after_done
        self.has_window = False

        with open(os.path.join(here, "reftest.js")) as f:
            self.script = f.read()
        with open(os.path.join(here, "reftest-wait_webdriver.js")) as f:
            self.wait_script = f.read()

    def is_alive(self):
        return self.protocol.is_alive()

    def do_test(self, test):
        self.logger.info("Test requires OS-level window focus")

        self.protocol.webdriver.set_window_size(600, 600)

        result = self.implementation.run_test(test)

        return self.convert_result(test, result)

    def screenshot(self, test, viewport_size, dpi):
        # https://github.com/w3c/wptrunner/issues/166
        assert viewport_size is None
        assert dpi is None

        return WebDriverRun(self._screenshot,
                           self.protocol.webdriver,
                           self.test_url(test),
                           test.timeout).run()

    def _screenshot(self, webdriver, url, timeout):
        webdriver.get(url)

        webdriver.execute_async_script(self.wait_script)

        screenshot = webdriver.get_screenshot_as_base64()

        # strip off the data:img/png, part of the url
        if screenshot.startswith("data:image/png;base64,"):
            screenshot = screenshot.split(",", 1)[1]

        return screenshot
