from . import ffi, lib

ffi_new = ffi.new
NULL = ffi.NULL


# A similar object will eventually make it to the GraphBLAS spec.
# Hide this from the user for now.
class _CArray:
    def __init__(self, index, ctype="GrB_Index", name=None):
        self.index = index
        self._carg = ffi_new(f"{ctype}[]", index)
        self.ctype = ctype
        self._name = name

    @property
    def name(self):
        if self._name is not None:
            return self._name
        if len(self.index) < 20:
            values = ", ".join(map(str, self.index))
        else:
            values = (
                f"{', '.join(map(str, self.index[:5]))}, "
                "..., "
                f"{', '.join(map(str, self.index[-5:]))}"
            )
        return "(%s[]){%s}" % (self.ctype, values)

    __hash__ = None


class _AllIndices:
    def __init__(self):
        self._carg = lib.GrB_ALL
        self.name = "GrB_ALL"


_ALL_INDICES = _AllIndices()


class IndexerResolver:
    def __init__(self, obj, indices):
        if obj._is_scalar:
            raise TypeError("Cannot index into Scalars")
        self.obj = obj
        self.indices = self.parse_indices(indices, obj.shape)

    @property
    def is_single_element(self):
        for idx, size in self.indices:
            if size is not None:
                return False
        return True

    def parse_indices(self, indices, shape):
        """
        Returns
            [(rows, rowsize), (cols, colsize)] for Matrix
            [(idx, idx_size)] for Vector

        Within each tuple, if the index is of type int, the size will be None
        """
        if len(shape) == 1:
            if type(indices) is tuple:
                raise TypeError(f"Index for {type(self.obj).__name__} cannot be a tuple")
            # Convert to tuple for consistent processing
            indices = (indices,)
        elif len(shape) == 2:
            if type(indices) is not tuple or len(indices) != 2:
                raise TypeError(f"Index for {type(self.obj).__name__} must be a 2-tuple")

        out = []
        for i, idx in enumerate(indices):
            typ = type(idx)
            if typ is tuple:
                raise TypeError(
                    f"Index in position {i} cannot be a tuple; must use slice or list or int"
                )
            out.append(self.parse_index(idx, typ, shape[i]))
        return out

    def parse_index(self, index, typ, size):
        from .scalar import _CScalar

        if typ is int:
            if index >= size:
                raise IndexError(f"index={index}, size={size}")
            return _CScalar(index), None
        if typ is slice:
            if index == slice(None):
                # [:] means all indices; use special GrB_ALL indicator
                return _ALL_INDICES, _CScalar(size)
            index = tuple(range(size)[index])
        elif typ is not list:
            try:
                index = tuple(index)
            except Exception:
                raise TypeError("Unable to convert to tuple")
        return _CArray(index), _CScalar(len(index))


class AmbiguousAssignOrExtract:
    def __init__(self, parent, resolved_indexes):
        self.parent = parent
        self.resolved_indexes = resolved_indexes

    def __call__(self, *args, **kwargs):
        if type(self.parent) is Updater:
            parent_kwargs = []
            if self.parent.kwargs["accum"] is not None:
                parent_kwargs.append(f"accum={self.parent.kwargs['accum']}")
            if self.parent.kwargs["mask"] is not None:
                # It would sure be nice if we knew the mask type.
                # Passing around C objects directly is sometimes inconvenient.
                parent_kwargs.append("mask=<Mask>")
                parent_kwargs.append(f"replace={self.parent.kwargs['replace']}")
            if not parent_kwargs:
                raise ValueError("GraphBLAS object already called (with no keywords)")
            parent_kwargs = ", ".join(parent_kwargs)
            raise ValueError(f"GraphBLAS object already called with keywords: {parent_kwargs}")
        # Occurs when user calls C[index](params)
        # Reverse the call order so we can parse the call args and kwargs
        updater = self.parent(*args, **kwargs)
        return updater[self.resolved_indexes]

    def __lshift__(self, obj):
        # Occurs when user calls C(params)[index] << obj or C[index] << obj
        # Delegate back to parent's __setitem__ method
        self.parent[self.resolved_indexes] = obj

    def update(self, obj):
        # Occurs when user calls C(params)[index].update(obj) or C[index].update(obj)
        # Delegate back to parent's __setitem__ method
        self.parent[self.resolved_indexes] = obj

    @property
    def value(self):
        if type(self.parent) is Updater:
            raise TypeError("Cannot extract from an Updater")
        if not self.resolved_indexes.is_single_element:
            raise AttributeError("Only Scalars have `.value` attribute")
        scalar = self.parent._extract_element(self.resolved_indexes, name="s_extract")
        return scalar.value

    def new(self, *, dtype=None, mask=None, name=None):
        """
        Force extraction of the indexes into a new object
        dtype and mask are the only controllable parameters.
        """
        if type(self.parent) is Updater:
            raise TypeError("Cannot extract from an Updater")
        if self.resolved_indexes.is_single_element:
            if mask is not None:
                raise TypeError("mask is not allowed for single element extraction")
            return self.parent._extract_element(self.resolved_indexes, dtype=dtype, name=name)
        else:
            delayed_extractor = self.parent._prep_for_extract(self.resolved_indexes)
            return delayed_extractor.new(dtype=dtype, mask=mask, name=name)

    def _extract_delayed(self):
        """Return an Expression object, treating this as an extract call"""
        if type(self.parent) is Updater:
            raise TypeError("Cannot extract from an Updater")
        return self.parent._prep_for_extract(self.resolved_indexes)


class Updater:
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = kwargs

    def __getitem__(self, keys):
        # Occurs when user calls C(params)[index]
        # Need something prepared to receive `<<` or `.update()`
        if self.parent._is_scalar:
            raise TypeError("Indexing not supported for Scalars")
        if type(keys) is IndexerResolver:
            resolved_indexes = keys
        else:
            resolved_indexes = IndexerResolver(self.parent, keys)
        return AmbiguousAssignOrExtract(self, resolved_indexes)

    def __setitem__(self, keys, obj):
        # Occurs when user calls C(params)[index] = delayed
        if self.parent._is_scalar:
            raise TypeError("Indexing not supported for Scalars")
        if type(keys) is IndexerResolver:
            resolved_indexes = keys
        else:
            resolved_indexes = IndexerResolver(self.parent, keys)

        if resolved_indexes.is_single_element and not self.kwargs:
            # Fast path using assignElement
            self.parent._assign_element(resolved_indexes, obj)
        else:
            delayed = self.parent._prep_for_assign(resolved_indexes, obj)
            self.update(delayed)

    def __delitem__(self, keys):
        # Occurs when user calls `del C(params)[index]`
        if self.parent._is_scalar:
            raise TypeError("Indexing not supported for Scalars")
        if type(keys) is IndexerResolver:
            resolved_indexes = keys
        else:
            resolved_indexes = IndexerResolver(self.parent, keys)

        if resolved_indexes.is_single_element:
            self.parent._delete_element(resolved_indexes)
        else:
            raise TypeError("Remove Element only supports a single index")

    def __lshift__(self, delayed):
        # Occurs when user calls C(params) << delayed
        self.parent._update(delayed, **self.kwargs)

    def update(self, delayed):
        # Occurs when user calls C(params).update(delayed)
        self.parent._update(delayed, **self.kwargs)
