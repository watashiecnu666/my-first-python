class Calculator:
    name='hahaha'
    def _init_(self,name,price,height,weight):
       self.name=name
       self.price=price
       self.h=height
       self.w=weight
    def add(self,x,y):
        print(self.name)
        result=x+y
        print(result)
    def minus(self,x,y):
        result=x-y
        print(result)
    def times(self,x,y):
        print(x*y)
    def divide(self,x,y):
        print(x/y)
    
