"""mprpc的python服务端.
>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

Python服务端只支持python3.6+,使用asyncio实现

+ File: server.__init__.py
+ Version: 0.5
+ Author: hsz
+ Email: hsz1273327@gmail.com
+ Copyright: 2018-02-08 hsz
+ License: MIT
+ History

    + 2018-01-23 created by hsz
    + 2018-02-08 version-0.5 by hsz


使用方式
::::::::::::::::::::

.. code:: python

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
        pass


    with MyMPRPCServer(("127.0.0.1", 5000), debug=True) as server:
        server.register_introspection_functions()

        @server.register_function()
        def testfunc(a, b):
            '''有help'''
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


"""
import logging.config
from .log import LOGGING_CONFIG_DEFAULTS
from .server import BaseServer as SimpleMprpcServer
logging.config.dictConfig(LOGGING_CONFIG_DEFAULTS)


__all__ = ["SimpleMprpcServer"]
