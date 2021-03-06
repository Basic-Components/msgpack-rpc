import platform
from pymprpc.server import SimpleMprpcServer
if platform.system() == "Windows":
    try:
        import aio_windows_patch as asyncio
    except:
        import warnings
        warnings.warn(
            "you should install aio_windows_patch to support windows",
            RuntimeWarning,
            stacklevel=3)
        import asyncio

else:
    import asyncio
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass


class MyMPRPCServer(SimpleMprpcServer):
    """MyMPRPServer.

    测试用的

    """
    version = "0.0.2"


with MyMPRPCServer(("127.0.0.1", 5000), debug=True) as server:
    server.register_introspection_functions()

    @server.register_function()
    def testfunc(a, b):
        """有help
        """
        return a + b

    @server.register_function()
    async def testcoro(a, b):
        await asyncio.sleep(0.1)
        return a + b

    @server.register_function()
    async def testcorogen(a, b):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield i + a + b

    class TestClass:

        def testclassmethod(self, a, b):
            return a + b

        async def testclasscoro(self, a, b):
            await asyncio.sleep(0.1)
            return a + b

        async def testclasscorogen(self, a, b):
            for i in range(10):
                await asyncio.sleep(0.1)
                yield i + a + b

    t = TestClass()
    server.register_instance(t)
    server.run_forever()
