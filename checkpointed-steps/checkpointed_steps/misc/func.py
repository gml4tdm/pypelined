from __future__ import annotations

import abc
import inspect
import pickle

import types
import typing

import checkpointed
from checkpointed import PipelineStep
from checkpointed.arg_spec import constraints as _constraints
from checkpointed.arg_spec import arguments as _arguments

__all__ = ['pipeline_step', 'pickle_loader', 'pickle_saver']


def pickle_loader(path: str) -> typing.Any:
    with open(path, 'rb') as file:
        return pickle.load(file)


def pickle_saver(path: str, result: typing.Any):
    with open(path, 'wb') as file:
        pickle.dump(result, file)


def pipeline_step(*,
                  save_func,
                  load_func,
                  supported_input_steps,
                  marker_classes,
                  is_pure=False,
                  arguments=None,
                  constraints=None) -> typing.Callable[[types.FunctionType], type[FunctionStepBase]]:
    """Decorator to wrap single functions for use as a step
    in a pipeline.

    WARNING: This will make the function unusable as a regular function.

    Caching is done on a best-effort basis: inspect.getsource() is used to
    calculate a hash of the function source code.
    If inspect.getsource() fails, caching will be disabled.
    """
    def decorator(func) -> type[FunctionStepBase]:
        try:
            source = inspect.getsource(func)
        except OSError:
            source = None
        if source is not None:
            hash_value = hash(source)
        else:
            hash_value = None
        wrapper = type(
            f'FunctionStepWrapper_{func.__name__}',
            (FunctionStepBase,) + tuple(marker_classes),
            {
                '$_function': func,
                '$_save_function': save_func,
                '$_load_function': load_func,
                '$_pure': is_pure,
                '$_arguments': arguments if arguments is not None else {},
                '$_constraints': constraints if constraints is not None else [],
                '$_supported_inputs': supported_input_steps,
                '$_hash': hash_value,
            }
        )
        return typing.cast(type[FunctionStepBase], wrapper)
    return decorator


class FunctionStepBase(checkpointed.PipelineStep, abc.ABC):

    @classmethod
    def supports_step_as_input(cls, step: type[PipelineStep]) -> bool:
        return getattr(cls, '$_supported_inputs')

    async def execute(self, *inputs) -> typing.Any:
        function = getattr(self, '$_function')
        return function(*inputs, conf=self.config)

    @classmethod
    def save_result(cls, path: str, result: typing.Any):
        function = getattr(cls, '$_save_function')
        function(path, result)

    @classmethod
    def load_result(cls, path: str):
        function = getattr(cls, '$_load_function')
        return function(path)

    @classmethod
    def is_deterministic(cls) -> bool:
        return getattr(cls, '$_pure', False)

    def get_checkpoint_metadata(self) -> typing.Any:
        return {
            'function_hash': getattr(self, '$_hash')
        }

    def checkpoint_is_valid(self, metadata: typing.Any) -> bool:
        h = getattr(self, '$_hash')
        return h is not None and h == metadata['function_hash']

    @classmethod
    def get_arguments(cls) -> dict[str, _arguments.Argument]:
        return getattr(cls, '$_arguments')

    @classmethod
    def get_constraints(cls) -> list[_constraints.Constraint]:
        return getattr(cls, '$_constraints')