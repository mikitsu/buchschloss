"""Validation"""

import re
from misc import Instance


class Validator:
    """Factory for a misc.validation.MultiValidator
        that guesses which validator to use
        """

    def __new__(cls, *checks):
        """Create a new mis.validation.MultiValidator guessing
            which validator to use

            `checks` are the arguments passed to the respective validator
                which one is determined automatically.
            """
        checks = checks + (None,)
        validators = []
        current = None
        stored = []
        for check in checks:
            if isinstance(check, (MultiValidator, TransformValidator, ConditionValidator)):
                validators.append(check)
                continue
            if check is None:
                val = None
            elif callable(check):
                val = TransformValidator
            elif isinstance(check[0], Instance):
                val = ConditionValidator
            elif isinstance(check[0], str):
                val = RegexValidator
            else:
                val = TransformValidator
            if val is not current:
                if current is not None:
                    validators.append(current(*stored))
                current = val
                stored = []
            stored.append(check)
        return MultiValidator(*validators)


class MultiValidator:
    """Chain multiple validators"""
    def __init__(self, *validators):
        """Create a new MultiValidator

            `validators` are single validators to be chained"""
        self.validators = validators

    def __call__(self, value):
        for validator in self.validators:
            good, value = validator(value)
            if not good:
                return False, value
        return True, value


class ConditionValidator:
    """validate based on a user-defined condition"""
    def __init__(self, *conditions):
        """Create a new ConditionValidator.

            `conditions` are iterables of the form
                (<condition>, <error message>), where <condition>
                is a delayed evaluation using `misc.Instance`
                that yields a value to used in boolean context
                indicating whether the value passed is valid
                e.g. Instance().attr['key'] == 'someval'
                <error message> is the error message to return
                if the condition resolves to a falsey value
            """
        self.conditions = conditions

    def __call__(self, value):
        for cond, msg in self.conditions:
            if not Instance.lookup(cond, value):
                return False, msg
        return True, value


class TransformValidator:
    """validate based on transformation"""
    def __init__(self, *transformations):
        """Create a new TransformValidator

            `transformations` are callables taking as single argument
                the user input and returning the transformed input.
                They may also be tuples of the form (<callable>, <config>)
                where <callale> is the callable described above
                and <config> is a mapping from exceptions that may occur
                during the transformation to error messages or tuples of
                multiple such exceptions.
                The default maps (ValueError, TypeError) to
                'Must be of type <name>' with <name> replaced by
                the callables __name__, making it suitable for types.

                Note: if a config (even if empty) is supplied,
                    it overrides the default.
            """
        default_config = {(ValueError, TypeError): 'Must be of type {__name__}'}
        self.trans = []
        self.configs = []
        for t in transformations:
            if isinstance(t, tuple):
                t, new_cnf = t
                self.configs.append(new_cnf)
            else:
                self.configs.append(default_config)
            self.trans.append(t)

    def __call__(self, value):
        for trans, cnf in zip(self.trans, self.configs):
            try:
                value = trans(value)
            except Exception as e:
                for exc, msg in cnf.items():
                    if isinstance(e, exc):
                        return False, msg.format(__name__=trans.__name__,
                                                 value=value,
                                                 )
                raise
        return True, value


class RegexValidator:
    """Factory for TransformValidators validating by regex"""
    class Error(Exception):
        pass

    def __new__(cls, *conditions):
        """Create a new TransformValidator validating
            the passed reular expressions

            `conditions` are (<regex>, <error>, [<group>]), <group> being
                optional, where <regex> is a regular expression in string form
                and <error> is the error message to display on failure
                of matching. <group> is the regex group to return.
                The default (if not given) is 0, returning the whole match.

            Note: while the verb "match" is used in this docstring,
                the re.search functionality is actually used for the validation
            """
        def creator(regex, error, group=0):
            def trans(value, _re=re.compile(regex), _group=group):
                try:
                    return _re.search(value).group(group)
                except AttributeError:
                    raise RegexValidator.Error from None

            return trans, {RegexValidator.Error: error}

        return TransformValidator(*[creator(*c) for c in conditions])
