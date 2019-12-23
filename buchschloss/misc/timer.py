from datetime import datetime, timedelta
import time

def basic_scheduler(ms, f):
    time.sleep(ms/1000)
    f()

def basic_message(title='', msg=''):
    print(title)
    print(msg)
    print(end='\a')

class Timer:
    scheduler = basic_scheduler
    messager = basic_message
    def __init__(self, time, text=None):
        self.duration = time
        self.text = text
        self.target = datetime.now()
        self.ticking = False

    def start(self):
        self.ticking = True
        self.target = datetime.now() + self.duration
        self.tick()

    def tick(self):
        now = datetime.now()
        if now > self.target:
            if self.text is not None:
                self.text.set(str(self.duration))
            Timer.messager('Time up', 'The timer {} has completed'.format(self.duration))
        else:
            if self.text is not None:
                self.text.set(str(self.target-now).split('.')[0])
            Timer.scheduler(200, self.tick)
        

if __name__ == '__main__':
    import tkinter as tk
    import tkinter.messagebox as tk_msg
    import tkinter.simpledialog as tk_dia
    
    root = tk.Tk()
    root.attributes('-topmost', True)
    root.option_add('*font', 'Times 20')

    def add_new():
        mins = tk_dia.askinteger('Minutes', 'Please insert the minutes for the new timer')
        if mins is None: return
        var = tk.StringVar(root, '---')
        tk.Button(root, command=Timer(timedelta(minutes=mins), var).start,
                  textvar=var).pack()

    tk.Button(root, text='add new', command=add_new).pack()

    Timer.scheduler = root.after
    Timer.messager = tk_msg.showinfo

    tk.mainloop()

