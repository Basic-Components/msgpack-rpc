import asyncio
from pymprpc import AsyncRPC


async def main(loop):
    async with AsyncRPC(
            addr="tcp://admin:admin@127.0.0.1:5000",
            loop=loop,
            debug=True) as rpc:
        print(await rpc.system.listMethods())
        print(await rpc.system.methodSignature("testclassmethod"))
        print(await rpc.system.methodHelp("testfunc"))
        print(await rpc.system.lenConnections())
        print(await rpc.system.lenUndoneTasks())
        print(await rpc.testclassmethod(1, 2))
        print(await rpc.testclasscoro(2, 3))
        print(await rpc.testcoro(5, 6))
        print(await rpc.testfunc(5, 4))
        agen = await rpc.testcorogen(1, 2)
        async for i in agen:
            print(i)

        await asyncio.sleep(200)
        print("wait done")

        # print(await rpc.testfunc())

    print("end")
loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(main(loop))
except Exception as e:
    raise e
