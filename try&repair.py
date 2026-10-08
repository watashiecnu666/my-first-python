try:
    file=open('eeee','r+')
except Exception as e:
    print('there is no file named as eeeeeeee')
    response=input('do you?')
    if response=='y':
        file=open('eee','w')
    else:
        pass
else:
    file.write('sssss')
file.close()
    
    
