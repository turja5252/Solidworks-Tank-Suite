class SolidWorksError(Exception):
    """Base error for SolidWorks session problems."""


class SolidWorksNotRunning(SolidWorksError):
    """SolidWorks is installed here but no session is open."""


class SolidWorksUnavailable(SolidWorksError):
    """This computer cannot talk to SolidWorks."""
