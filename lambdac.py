import os
import sys
from abc import ABC, abstractmethod
from typing import (
    Dict,
    Any,
    NamedTuple,
    Optional,
    Callable,
    TypedDict,
    Generic,
    TypeVar,
    Iterable,
    Sequence,
    Tuple,
    Union,
)
from pyparsing import (  # type: ignore
    Combine,
    Empty,
    Forward,
    Group,
    Keyword,
    LineEnd,
    Literal,
    NoMatch,
    ParserElement,
    ParseResults,
    Word,
    alphanums,
    alphas,
    nums,
    dblQuotedString,
    delimitedList,
    infixNotation,
    nums,
    oneOf,
    opAssoc,
    restOfLine,
    ungroup,
)
from collections import namedtuple
from functools import reduce
from pprint import pprint


_bound_vars = set()


def _next_var(v: "Var") -> "Var":
    """
    Return the next letter

    >>> _next_var(Var("u"))
    v

    >>> _next_var(Var("z"))
    u
    """
    global _bound_vars
    first = ord("u")
    last = ord("z")
    index = ord(v.name)
    while True:
        next_ = ord(v.name) + 1
        if next_ > last:
            next_ = first
        found = Var(chr(next_))
        if found not in _bound_vars:
            return Var(chr(next_))


def _reset_bound_vars():
    global _bound_vars
    _bound_vars = set()


def _bind(var: "Var"):
    _bound_vars.add(var.name)


class Term:
    def replace(self, old, new) -> "Term":
        pass

    @property
    def is_norm(self) -> bool:
        """
        >>> Lamb(Var("x"), Var("x")).is_norm
        True
        >>> Var("x").is_norm
        True
        >>> Val("1").is_norm
        True
        >>> Appl(Lamb(Var("x"), Var("x")), Val("1")).is_norm
        False
        """
        if isinstance(self, Appl):
            if isinstance(self.e1, Lamb):
                return False
            else:
                return self.e1.is_norm and self.e2.is_norm
        return True


class Var(Term):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    def replace(self, old, new) -> "Term":
        if self.name == old.name:
            return new
        return self


class Val(Var):
    def __init__(self, val):
        super().__init__(val)


class Lamb(Term):
    body: Term

    def __init__(self, var: Var, body: Term):
        self.var = var
        self.body = body
        _bind(self.var)

    def replace(self, old: Var, new: Term) -> "Term":
        if isinstance(new, Var) and new.name == self.var.name:
            # alpha conversion
            old_var = self.var
            self.var = _next_var(self.var)
            self.body = self.body.replace(old_var, self.var)
        self.body = self.body.replace(old, new)
        return self

    def __repr__(self):
        return f"(λ{self.var}.{self.body})"


class Appl(Term):
    def __init__(self, e1, e2):
        self.e1 = e1
        self.e2 = e2

    def replace(self, old, new):
        self.e1 = self.e1.replace(old, new)
        self.e2 = self.e2.replace(old, new)
        return self

    def __repr__(self):
        if isinstance(self.e2, Appl):
            return f"{self.e1} ({self.e2})"
        return f"{self.e1} {self.e2}"


def appl(lam: "Lamb", term: Term):
    """
    >>> appl(Lamb(Var("x"), Var("x")), Val("1"))
    1
    >>> appl(Lamb(Var("x"), Lamb( Var("y"), Appl(Var("x"), Var("y")) )), Val("1"))
    (λy.1 y)

    >>> appl(Lamb(Var("x"), Lamb( Var("y"), Appl(Var("x"), Var("y")) )), Var("y"))
    (λz.y z)

    >>> appl(Lamb(Var("x"), Var("x")), Lamb(Var("y"), Var("y")))
    (λy.y)
    """
    res = lam.replace(lam.var, term)
    if isinstance(res, Lamb):
        return res.body

    raise TypeError(f"{res} is not a lambda")


def eval_term(term: Term) -> Term:
    """
    Abstration evaluate to it self
    >>> eval_term(Lamb(Var("x"), Var("x")))
    (λx.x)

    Value evaluate to it self
    >>> eval_term(Appl(Lamb(Var("x"), Var("x")), Val("1")))
    1

    Application evalute by CBV
    >>> eval_term(Appl(Lamb(Var("x"), Var("x")), Lamb(Var("y"), Var("y"))))
    (λy.y)
    """
    if isinstance(term, Appl):
        e1 = eval_term(term.e1)
        e2 = eval_term(term.e2)
        if isinstance(e1, Lamb):
            return appl(e1, e2)
    return term


class AST:
    def __init__(self, parse_tree: ParseResults):
        self.parse_results = parse_tree

    def eval(self):
        """
        I
        >>> parse("(fn x => x) 1").eval()
        1

        K combinator
        >>> parse("(fn x => fn y => x) 1 2").eval()
        1

        S combinator
        >>> parse("(fn x => fn y => fn z => x z (y z)) (fn x => fn y => x) (fn x => x) 1").eval()
        """
        _reset_bound_vars()
        while not t.is_norm:
            t = eval_term(t)
        return t


def BNF() -> ParserElement:
    """
    Our grammar
    """
    if hasattr(BNF, "cache"):
        return BNF.cache  # type: ignore

    def to_lambda(t):
        return Lamb(Var(t.arg), t.body.asList()[0])

    def to_application(t):
        # Left associativity
        return reduce(Appl, t)

    def to_variable(t) -> Var:
        return Var(t[0])

    def to_val(t) -> Val:
        return Val(t[0])

    ID = Word(alphas, exact=1)
    VAL = Word(nums)
    FN = Literal("fn").suppress()
    ARROW = Literal("=>").suppress()
    LP = Literal("(").suppress()
    RP = Literal(")").suppress()

    comment = Literal("#").suppress() + restOfLine

    term = Forward()
    appl_ = Forward()

    # abst ::= "fn" ID "=>" term+
    abst = FN + ID("arg") + ARROW + term[1, ...]("body")

    var = ID | VAL | LP + term + RP

    appl_ <<= var + appl_[...]  # applseq("e2")
    appl = appl_ | NoMatch()  # add no match to create a new rule

    term <<= abst | appl | var

    term.ignore(comment)
    ID.setParseAction(to_variable)
    VAL.setParseAction(to_val)
    abst.setParseAction(to_lambda)
    appl.setParseAction(to_application)

    term.validate()

    BNF.cache = term  # type: ignore

    return term


def parse(input: str) -> AST:
    return AST(BNF().parseString(input, True))


if __name__ == "__main__":
    BNF().runTests(
        """
       # Simple abstraction
       fn x => x y y

       # Chainned abstrxction
       fn x => fn y => x y

       # Abstraction application
       (fn x => x y) (fn x => x)

       # Try left associativity of appliction
       u v w x y z

       # Simple xpplicxtion
       (fn x => x) a

       # ɑ conversion needed
       (fn x => x y) a

       # Value
       1

       # Parenthesis
       x z (y z)
       """
    )

    # Testing parsing and application
    print(">>>", appl(BNF().parseString("fn x => fn y => x y", True)[0], Var("1")))
