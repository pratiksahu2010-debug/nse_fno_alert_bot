from abc import ABC,abstractmethod
class Strategy(ABC):
    name="BASE"
    @abstractmethod
    def evaluate(self,*args,**kwargs): ...
