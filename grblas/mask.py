class Mask:
    complement = False
    structure = False
    value = False

    def __init__(self, mask):
        self.mask = mask

    def __eq__(self, other):
        raise TypeError(f"__eq__ not defined for objects of type {type(self)}.")

    def __bool__(self):
        raise TypeError(f"__bool__ not defined for objects of type {type(self)}.")

    def __repr__(self):
        return self.mask.__repr__(mask=self)

    def _repr_html_(self):
        return self.mask._repr_html_(mask=self)

    @property
    def _carg(self):
        return self.mask.gb_obj[0]


class StructuralMask(Mask):
    complement = False
    structure = True
    value = False

    def __invert__(self):
        return ComplementedStructuralMask(self.mask)

    @property
    def name(self):
        return f"{self.mask.name}.S"

    @property
    def _name_html(self):
        return f"{self.mask._name_html}.S"


class ValueMask(Mask):
    complement = False
    structure = False
    value = True

    def __invert__(self):
        return ComplementedValueMask(self.mask)

    @property
    def name(self):
        return f"{self.mask.name}.V"

    @property
    def _name_html(self):
        return f"{self.mask._name_html}.V"


class ComplementedStructuralMask(Mask):
    complement = True
    structure = True
    value = False

    def __invert__(self):
        return StructuralMask(self.mask)

    @property
    def name(self):
        return f"~{self.mask.name}.S"

    @property
    def _name_html(self):
        return f"~{self.mask._name_html}.S"


class ComplementedValueMask(Mask):
    complement = True
    structure = False
    value = True

    def __invert__(self):
        return ValueMask(self.mask)

    @property
    def name(self):
        return f"~{self.mask.name}.V"

    @property
    def _name_html(self):
        return f"~{self.mask._name_html}.V"
