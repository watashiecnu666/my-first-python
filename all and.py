X=100

def f():
    global a
    a=1000
    print(a)
    return a+10000

print(f())
