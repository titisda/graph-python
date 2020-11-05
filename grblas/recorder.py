import collections
from . import base, lib
from .base import _recorder
from .dtypes import DataType
from .mask import Mask
from .matrix import TransposedMatrix
from .ops import TypedOpBase


def gbstr(arg):
    """ Convert arg to a string as an argument in a GraphBLAS call"""
    if arg is None:
        return "NULL"
    elif isinstance(arg, TypedOpBase):
        name = arg.gb_name
    elif isinstance(arg, Mask):
        name = arg.mask.name
    elif type(arg) is TransposedMatrix:
        name = arg._matrix.name
    elif type(arg) is DataType:
        name = arg.gb_name
    else:
        name = arg.name
    if not name:
        return f"temp_{type(arg).__name__.lower()}"
    return name


class Recorder:
    """Record GraphBLAS C calls.

    The recorder can use `.start()` and `.stop()` to enable/disable recording,
    or it can be used as a context manager.

    For example,

    >>> with Recorder() as rec:
    ...     C = A.mxm(B).new()
    >>> rec.data[0]
    'GrB_mxm(C, NULL, NULL, GxB_PLUS_TIMES_INT64, A, B, NULL)'

    Currently, only one recorder will record at a time within a context.
    """

    def __init__(self, *, record=False, max_rows=20):
        self.data = []
        self._token = None
        self.max_rows = max_rows
        if record:
            self.start()

    def record(self, cfunc_name, args):
        if not hasattr(lib, cfunc_name):
            cfunc_name = f"GxB_{cfunc_name[4:]}"
        self.data.append(f'{cfunc_name}({", ".join(gbstr(x) for x in args)});')
        base._prev_recorder = self

    def start(self):
        if self._token is None:
            self._token = _recorder.set(self)
        base._prev_recorder = self

    def stop(self):
        if self._token is not None:
            _recorder.reset(self._token)
            self._token = None
        if base._prev_recorder is self or base._prev_recorder is None:
            base._prev_recorder = _recorder.get(None)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type_, value, traceback):
        self.stop()

    def __iter__(self):
        yield from self.data

    @property
    def is_recording(self):
        return self._token is not None and _recorder.get(base._prev_recorder) is self

    def _repr_markdown_(self):
        # Syntax highlighting from github-flavored markdown looks better than
        # using IPython.display.Code or pygments
        from .formatting import CSS_STYLE

        status = (
            '<div style="'
            "height: 12px; "
            "width: 12px; "
            "display: inline-block; "
            "vertical-align: middle; "
            "margin-left: 2px; "
            "%s"
            '"></div>'
        )
        if self.is_recording:
            # red circle for recording
            status = status % ("background-color: red; " "border-radius: 50%;")
        else:
            # two vertical bars for paused
            status = status % ("border-right: 5px solid gray; " "border-left: 5px solid gray;")
        lines = [
            "<div>",
            f"{CSS_STYLE}",
            '<details open class="gb-arg-details">',
            '<summary class="gb-arg-summary">',
            '<table class="gb-info-table" style="display: inline-block; vertical-align: middle;">',
            "<tr><td>",
            "<tt>grblas.Recorder</tt>",
            status,
            "</td></tr>",
            "</table>",
            "</summary>",
            '<blockquote class="gb-expr-blockquote" style="margin-left: -8px;">',
            "",
            "```C",
            "  " + "\n  ".join(self.data),
            "```",
            "</blockquote>",
            "</details>",
            "</div>",
        ]
        return "\n".join(lines)

    def __repr__(self):
        lines = [f'grblas.Recorder ({"" if self.is_recording else "not "}recording)']
        lines.append("-" * len(lines[0]))
        if self.max_rows is not None and len(self.data) > self.max_rows:
            lines.extend(f"  {line}" for line in self.data[: self.max_rows // 2])
            lines.append("")
            lines.append(f"  ... ({len(self.data) - self.max_rows} rows not shown)")
            lines.append("")
            lines.extend(f"  {line}" for line in self.data[-((self.max_rows + 1) // 2) :])
        else:
            lines.extend(f"  {line}" for line in self.data)
        return "\n".join(lines)


skip_record = Recorder()
skip_record.data = collections.deque([], 0)
