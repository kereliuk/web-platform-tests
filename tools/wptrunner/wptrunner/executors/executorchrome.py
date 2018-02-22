from ..webdriver_server import ChromeDriverServer
from .base import WdspecExecutor, WebDriverProtocol
from .executorwebdriver import WebDriverTestharnessExecutor


class ChromeDriverProtocol(WebDriverProtocol):
    server_cls = ChromeDriverServer

class ChromeDriverWdspecExecutor(WdspecExecutor):
    protocol_cls = ChromeDriverProtocol

class ChromeDriverTestHarnessExecutor(WebDriverTestharnessExecutor):
    protocol_cls = ChromeDriverProtocol
