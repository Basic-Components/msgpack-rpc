import time
from pymprpc.client import RPC


def main():
    with RPC(addr="tcp://admin:admin@127.0.0.1:5000",
             debug=True) as rpc:
        print(rpc.system.listMethods())
        print(rpc.system.methodSignature("testclassmethod"))
        print(rpc.system.methodHelp("testfunc"))
        print(rpc.system.lenConnections())
        print(rpc.system.lenUndoneTasks())
        print(rpc.testclassmethod(1, 2))
        print(rpc.testclasscoro(2, 3))
        print(rpc.testcoro(5, 6))
        print(rpc.testfunc(5, 4))
        agen = rpc.testcorogen(1, 2)
        for i in agen:
            print(i)
        # time.sleep(200)
        # print("wait done")
        # # rpc.close()
        # print(rpc.testfunc())

    print("end")


if __name__ == "__main__":
    main()
