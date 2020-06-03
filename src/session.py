"""Experimental design for handling provenance using W3C PROV.

"""

import datetime
import hashlib
import typing

import prov.model as prov
from xarray import DataArray

import utilities

__author__ = "Marco Sertoli"
__credits__ = ["Chris MacMackin", "Marco Sertoli"]


global_session = None


def get_dependency_data():
    """A generator for provenance data on dependencies."""
    raise NotImplementedError("TODO: write this function")


def hash_vals(**kwargs: typing.Dict[str, typing.Any]) -> str:
    """Produces an SHA256 hash from the key-value pairs passed as
    arguments.

    Parameters
    ---------
    kwargs
        The data to use for the hash.

    Returns
    -------
    str
        A hexadecimal representation of the hash.
    """
    hash_result = hashlib.sha256()
    for key, val in kwargs:
        hash_result.update(bytes(key, encoding="utf-8"))
        hash_result.update(b":")
        hash_result.update(bytes(str(val), encoding="utf-8"))
        hash_result.update(b",")
    return hash_result.hexdigest()


class Session:
    """A class handling information about the use of the software. Mostly
    this is for purposes of provenance.

    Parameters
    ----------
    user_orcid: str
        The ORCiD ID for the person using the software.

    Attributes
    ----------
    prov: prov.model.ProvDocument
        The document containing all of the provenance information for this
        session.
    session: prov.model.ProvActivity
        The provenance Activity object representing this session. It should
        contain information about versions of different libraries being used.

    """

    def __init__(self, user_orcid: str):
        self.prov = prov.ProvDocument()
        self.prov.set_default_namespace('https://ccfe.ukaea.uk/')
        self.prov.add_namespace('orcid', 'https://orcid.org/')
        self._user = [self.prov.agent('orcid:' + user_orcid)]
        date = datetime.datetime.now()
        session_properties = {'os': None, 'directory': None, 'host': None}
        session_id = hash_vals(startTime=date, **session_properties)
        self.session = self.prov.activity(session_id, date, None,
                                          session_properties)
        self.prov.association(self.session, self._user[0])

    def __enter__(self):
        global global_session
        self.old_global_session = global_session
        global_session = self
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        global global_session
        global_session = self.old_global_session
        return False

    @property
    def agent(self) -> prov.ProvAgent:
        """The agent (person or piece of software) currently in immediate
        control of execution.

        :returntype: prov.model.ProvAgent

        """
        return self._user[-1]

    def push_agent(self, agent: prov.ProvAgent):
        """Delegate responsibility to another agent.

        They will appear to be in control of execution now and will be
        returned by the :py:meth:`agent` property.

        Parameters
        ----------
        agent
            The new agent to delegate responsibilityt to.

        """
        agent.actedOnBehalfOf(self._user[-1])
        self._user.append(agent)

    def pop_agent(self) -> prov.ProvAgent:
        """Take responsibility back from the Agent that it was most recently
        delegated to.

        The Agent which the responsibility was delegated by will now
        appear to be in control of execution and will be the one
        returned by the :py:meth:`agent` property.

        Returns
        -------
        prov.ProvAgent
            The agent that responsibility was taken away from.

        """
        return self._user.pop()

    @classmethod
    def begin(cls, user_orcid: str):
        """Sets up a global session, without bothering with a context
        manager.

        Parameters
        ----------
        user_orcid
            The ORCiD ID for the person using the software.

        """
        global global_session
        global_session = cls(user_orcid)


def generate_prov(func, pass_sess=False):
    """Decorator to be applied to functions generating
    :py:class:`xarray.DataArray` output. It will produce PROV data and
    attach it as an attribute.

    This should only be applied to stateless functions, as the PROV
    data it generates will not accurately describe anything else.

    Parameters
    ----------
    func
        A function of arbitrary signature, but returning at least one
        :py:class:`xarray.DataArray` obejcts.
    pass_sess
        Indicates whether, if a keyword argument called ``sess`` is present,
        it should be passed to ``func``.

    """

    param_names, var_positional = utilities.positional_parameters(func)
    num_positional = len(var_positional)

    def wrapper(*args, **kwargs):
        session = kwargs.get("sess", global_session)
        if "sess" in kwargs and not pass_sess:
            kwargs = dict(kwargs)
            del kwargs["sess"]
        start_time = datetime.datetime.now()

        result = func(*args, **kwargs)

        end_time = datetime.datetime.now()
        args_prov = []
        activity_attrs = {prov.PROV_TYPE: func.__name__}
        id_attrs = {}
        for i, arg in enumerate(args):
            if i < num_positional:
                argname = param_names[i]
            else:
                argname = var_positional + str(i - num_positional)
            if isinstance(arg, DataArray):
                args_prov.append(arg.attrs["provenance"])
                id_attrs[argname] = args_prov[-1].identifier
            else:
                args_prov[argname] = str(arg)
                activity_attrs[argname] = str(arg)
        for key, val in kwargs.items():
            if isinstance(arg, DataArray):
                args_prov.append(val.attrs["provenance"])
                id_attrs[key] = args_prov[-1].identifier
            else:
                args_prov[key] = str(key)
                activity_attrs[val] = str(arg)
        generated_array = False
        activity_id = hash_vals(agent=session.agent, date=end_time, **id_attrs)
        activity = session.prov.activity(activity_id, start_time, end_time,
                                         activity_attrs)
        if isinstance(result, tuple):
            entity_id = hash_vals(activity=activity_id, name=result.name,
                                  **id_attrs)
            entity = session.prov.entity(entity_id)
            entity.wasGeneratedBy(activity, end_time)
            entity.wasAttributedTo(session.agent)
            result.attrs["provenance"] = entity
        elif isinstance(result, DataArray):
            for i, r in enumerate(result):
                if isinstance(r, DataArray):
                    entity_id = hash_vals(activity=activity_id,
                                          position=str(i), name=r.name,
                                          **id_attrs)
                    entity = session.prov.entity(entity_id)
                    entity.wasGeneratedBy(activity, end_time)
                    entity.wasAttributedTo(session.agent)
                    r.attrs["provenance"] = entity
        if not generated_array:
            raise ValueError("No DataArray object was produced by the "
                             "function. Can not assign PROV data.")
        return result

    return wrapper