"""Практична робота №3: metaprogramming and patterns demonstration."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from hashlib import sha256
from time import monotonic
from typing import Callable, ClassVar

# 1.1 Metaclass: validate and register plugins.
class PluginMeta(type):
    registry: ClassVar[dict[str, type]] = {}
    def __new__(mcls, name, bases, namespace):
        cls = super().__new__(mcls, name, bases, namespace)
        if bases and not namespace.get("abstract", False):
            for attr in ("name", "version", "execute"):
                if attr not in namespace: raise TypeError(f"{name}: missing {attr}")
            key = namespace["name"]
            if key in mcls.registry: raise TypeError(f"duplicate plugin: {key}")
            mcls.registry[key] = cls
        return cls
    def get_registry(cls): return dict(cls.registry)
    @classmethod
    def create_plugin(mcls, name): return mcls.registry[name]()
class Plugin(metaclass=PluginMeta): abstract = True
class UpperPlugin(Plugin):
    name="upper"; version="1.0"
    def execute(self, data): return data.upper()
class ReversePlugin(Plugin):
    name="reverse"; version="1.0"
    def execute(self, data): return data[::-1]
class CensorPlugin(Plugin):
    name="censor"; version="1.1"
    def execute(self, data):
        for word in ("secret", "пароль"): data=data.replace(word,"***")
        return data
HashPlugin = type("HashPlugin", (Plugin,), {"name":"hash", "version":"2.0", "execute":lambda self,data: sha256(data.encode()).hexdigest()[:12]})

# 1.2 Easier subclass hook and validated descriptor.
class RequiredText:
    def __set_name__(self, owner, name): self.name=name; self.storage="_"+name
    def __get__(self, obj, owner=None): return self if obj is None else getattr(obj,self.storage)
    def __set__(self,obj,value):
        if not isinstance(value,str) or not value.strip(): raise ValueError(f"{self.name} must be non-empty text")
        setattr(obj,self.storage,value.strip())
class Handler:
    registry: ClassVar[dict[str,type]]={}
    topic=RequiredText()
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "DefaultHandler":
            if not cls.__dict__.get("topic"): raise TypeError("handler must declare topic")
            Handler.registry[cls.topic]=cls
    def handle(self,message): raise NotImplementedError
class WelcomeHandler(Handler):
    topic="welcome"
    def handle(self,message): return f"Вітаю: {message}"

# 2.1 Function decorators: memoization, rate limiting, logging.
def cache(fn):
    memo={}
    @wraps(fn)
    def wrapper(*args,**kwargs):
        key=(args,tuple(sorted(kwargs.items())))
        if key not in memo: memo[key]=fn(*args,**kwargs)
        return memo[key]
    wrapper.cache=memo
    return wrapper
def rate_limit(calls:int, period:float):
    def decorate(fn):
        stamps=[]
        @wraps(fn)
        def wrapper(*args,**kwargs):
            now=monotonic(); stamps[:]=[t for t in stamps if now-t<period]
            if len(stamps)>=calls: raise RuntimeError("rate limit exceeded")
            stamps.append(now); return fn(*args,**kwargs)
        return wrapper
    return decorate
def log(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        print(f"[LOG] {fn.__name__} called")
        return fn(*args,**kwargs)
    return wrapper
@cache
@log
def factorial(n:int)->int:
    if n<0: raise ValueError("n must be >= 0")
    result=1
    for value in range(2,n+1): result*=value
    return result
@rate_limit(2,60)
def ping(label): return f"pong:{label}"

# 2.2 Class decorators.
def auto_repr(cls):
    def __repr__(self):
        fields={k:v for k,v in vars(self).items() if not k.startswith("_")}
        return f"{cls.__name__}({', '.join(f'{k}={v!r}' for k,v in fields.items())})"
    cls.__repr__=__repr__; return cls
def frozen(cls):
    original_init=cls.__init__
    def init(self,*args,**kwargs):
        object.__setattr__(self,"_locked",False); original_init(self,*args,**kwargs); object.__setattr__(self,"_locked",True)
    def set_attr(self,name,value):
        if getattr(self,"_locked",False): raise AttributeError("object is frozen")
        object.__setattr__(self,name,value)
    cls.__init__=init; cls.__setattr__=set_attr; return cls
def log_methods(cls):
    for name,member in tuple(vars(cls).items()):
        if callable(member) and not name.startswith("_"):
            @wraps(member)
            def wrapped(self,*args,__fn=member,__name=name,**kwargs):
                print(f"[METHOD] {type(self).__name__}.{__name}"); return __fn(self,*args,**kwargs)
            setattr(cls,name,wrapped)
    return cls
@log_methods
@frozen
@auto_repr
class AppConfig:
    def __init__(self,app,version): self.app=app; self.version=version
    def summary(self): return f"{self.app} v{self.version}"

# 3.1 Singleton and Factory Method.
class SingletonMeta(type):
    _instances={}
    def __call__(cls,*args,**kwargs):
        if cls not in cls._instances: cls._instances[cls]=super().__call__(*args,**kwargs)
        return cls._instances[cls]
class AuditLog(metaclass=SingletonMeta):
    def __init__(self): self.entries=[]
    def write(self,text): self.entries.append(text)
FACTORIES={}
def register_format(name):
    def deco(cls): FACTORIES[name]=cls; return cls
    return deco
class Exporter(ABC):
    @abstractmethod
    def export(self,items): ...
@register_format("text")
class TextExporter(Exporter):
    def export(self,items): return " | ".join(items)
@register_format("json")
class JsonExporter(Exporter):
    def export(self,items): return "["+", ".join(repr(x) for x in items)+"]"
def create_exporter(name): return FACTORIES[name]()

# 3.2 Observer + Strategy + MVC.
class EventEmitter:
    def __init__(self): self._listeners={}
    def on(self,event,callback): self._listeners.setdefault(event,[]).append(callback)
    def off(self,event,callback):
        if callback in self._listeners.get(event,[]): self._listeners[event].remove(callback)
    def emit(self,event,*args):
        for callback in tuple(self._listeners.get(event,())): callback(*args)
@dataclass
class Task:
    title:str; priority:int; deadline:datetime; completed:bool=False
    created_at:datetime=field(default_factory=datetime.now)
class SortStrategy(ABC):
    @abstractmethod
    def sort(self,tasks): ...
class SortByPriority(SortStrategy):
    def sort(self,tasks): return sorted(tasks,key=lambda t:t.priority)
class SortByDeadline(SortStrategy):
    def sort(self,tasks): return sorted(tasks,key=lambda t:t.deadline)
class SortByCreationDate(SortStrategy):
    def sort(self,tasks): return sorted(tasks,key=lambda t:t.created_at,reverse=True)
class TaskModel(EventEmitter):
    def __init__(self): super().__init__(); self.tasks=[]
    def add_task(self,title,priority,deadline):
        if not title.strip() or priority not in range(1,6): raise ValueError("invalid task")
        task=Task(title,priority,deadline); self.tasks.append(task); self.emit("task_added",task); return task
    def complete_task(self,index):
        task=self.tasks[index]; task.completed=True; self.emit("task_completed",task)
    def get_tasks(self,active=False): return [t for t in self.tasks if not(active and t.completed)]
    def stats(self): return {"total":len(self.tasks),"completed":sum(t.completed for t in self.tasks),"active":sum(not t.completed for t in self.tasks)}
class TaskView:
    def show_tasks(self,tasks,title="Tasks"):
        print(f"\n{title}: № | Назва | Пріоритет | Дедлайн | Стан")
        for i,t in enumerate(tasks,1): print(f"{i} | {t.title} | {t.priority} | {t.deadline:%d.%m} | {'✓' if t.completed else 'активне'}")
    def show_message(self,msg): print("[EVENT]",msg)
    def show_statistics(self,stats): print("Статистика:",stats)
class TaskController:
    def __init__(self,model,view):
        self.model=model; self.view=view; self.strategy=SortByPriority()
        model.on("task_added",lambda task:view.show_message(f"Додано: {task.title}"))
        model.on("task_completed",lambda task:view.show_message(f"Виконано: {task.title}"))
    def set_sort_strategy(self,strategy): self.strategy=strategy
    def add_task(self,*args): return self.model.add_task(*args)
    def complete_task(self,index): self.model.complete_task(index)
    def show_all(self): self.view.show_tasks(self.strategy.sort(self.model.get_tasks()))
    def show_active(self): self.view.show_tasks(self.strategy.sort(self.model.get_tasks(True)),"Активні завдання")
    def show_stats(self): self.view.show_statistics(self.model.stats())

def main():
    print("=== 1. Метаклас і плагіни ===")
    print("Реєстр:",list(PluginMeta.registry)); print("upper:",PluginMeta.create_plugin("upper").execute("hello")); print("hash:",PluginMeta.create_plugin("hash").execute("hello"))
    print("=== 2. __init_subclass__ і дескриптор ===")
    print("Обробник:",Handler.registry["welcome"]().handle("Арсеній"))
    print("=== 3. Декоратори функцій ===")
    print("5! =",factorial(5),"(повтор із кешу:",factorial(5),")")
    for label in ("A","B"): print(ping(label))
    try: ping("C")
    except RuntimeError as exc: print("Ліміт:",exc)
    print("=== 4. Декоратори класів ===")
    conf=AppConfig("PatternLab","1.0"); print(conf); print(conf.summary())
    try: conf.version="2.0"
    except AttributeError as exc: print("Замороження:",exc)
    print("=== 5. Singleton і Factory ===")
    print("Singleton:",AuditLog() is AuditLog()); print("Factory:",create_exporter("text").export(["A","B"]))
    print("=== 6. Observer, Strategy, MVC ===")
    model=TaskModel(); view=TaskView(); ctrl=TaskController(model,view); now=datetime.now()
    ctrl.add_task("Звіт",2,now+timedelta(days=2)); ctrl.add_task("Код",1,now+timedelta(days=1)); ctrl.add_task("Перевірка",3,now+timedelta(days=3))
    ctrl.show_all(); ctrl.set_sort_strategy(SortByDeadline()); ctrl.show_all(); ctrl.complete_task(0); ctrl.show_active(); ctrl.show_stats()
if __name__=="__main__": main()

