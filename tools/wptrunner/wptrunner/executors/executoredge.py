from ..webdriver_server import EdgeDriverServer
from .base import WdspecExecutor, WebDriverProtocol
from .executorwebdriver import WebDriverTestharnessExecutor, WebDriverExecutorProtocol

class EdgeDriverProtocol(WebDriverProtocol):
    server_cls = EdgeDriverServer


class EdgeDriverWdspecExecutor(WdspecExecutor):
    protocol_cls = EdgeDriverProtocol 

class EdgeDriverExecutorProtocol(WebDriverExecutorProtocol):
    server_cls = EdgeDriverServer

class EdgeDriverTestHarnessExecutor(WebDriverTestharnessExecutor):
    protocol_cls = EdgeDriverExecutorProtocol
