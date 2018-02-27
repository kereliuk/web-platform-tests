from ..webdriver_server import ChromeDriverServer
from .base import WdspecExecutor, WebDriverProtocol
from .executorwebdriver import WebDriverTestharnessExecutor, WebDriverExecutorProtocol


class ChromeDriverProtocol(WebDriverProtocol):
    server_cls = ChromeDriverServer

class ChromeDriverWdspecExecutor(WdspecExecutor):
    protocol_cls = ChromeDriverProtocol

class ChromeDriverExecutorProtocol(WebDriverExecutorProtocol):
    server_cls = ChromeDriverServer

class ChromeDriverTestHarnessExecutor(WebDriverTestharnessExecutor):
    protocol_cls = ChromeDriverExecutorProtocol
