"""Safe, actionable workflow errors without leaking prompts or private tracebacks."""


MEMORY_MESSAGE = 'Image generation needs more free memory. Completed work is kept; retry the image task after freeing memory.'


class WorkflowError(RuntimeError):
    def __init__(self, code, message, *, retryable=True):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable

    def public(self):
        return {'code': self.code, 'message': self.message, 'retryable': self.retryable}


def is_memory_error(exc):
    return type(exc).__name__ == 'OutOfMemoryError' or (isinstance(exc, InterruptedError) and 'reserve' in str(exc)) or (
        isinstance(exc, WorkflowError) and exc.code == 'image_memory')


def public_failure(exc):
    if isinstance(exc, WorkflowError):
        return exc.public()
    for child in getattr(exc, 'exceptions', ()):
        result = public_failure(child)
        if result['code'] != 'workflow_failed':
            return result
    if is_memory_error(exc) or (isinstance(exc, InterruptedError) and 'reserve' in str(exc)):
        return {'code': 'image_memory', 'message': MEMORY_MESSAGE, 'retryable': True}
    if type(exc).__name__ in ('ConnectError', 'ConnectTimeout', 'ReadTimeout', 'RemoteProtocolError') or getattr(getattr(exc, 'response', None), 'status_code', 0) >= 500:
        return {'code': 'local_service', 'message': 'A local model service did not respond. Retry the unfinished work.', 'retryable': True}
    return {'code': 'workflow_failed', 'message': 'This task could not finish. Completed work is kept; retry the unfinished work.', 'retryable': True}


def image_failure(job):
    value = job.get('failure') or {}
    allowed = {'image_memory', 'image_review', 'image_prompt', 'local_service', 'workflow_failed'}
    if value.get('code') in allowed and isinstance(value.get('message'), str):
        return WorkflowError(value['code'], value['message'], retryable=value.get('retryable') is True)
    if job.get('error') == 'OutOfMemoryError':
        return WorkflowError('image_memory', MEMORY_MESSAGE)
    return WorkflowError('workflow_failed', 'The image task could not finish. Retry the unfinished work.')
