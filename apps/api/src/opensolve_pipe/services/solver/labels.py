"""Names of a connection's pipe segments and fittings in traces, flags and topology issues.

They are numbered from 1, as the web app numbers them (the piping editor and the results
tables: "Pipe 1", "fitting 1"), so a message names the pipe the user sees. Data indexes stay
0-based array indexes: ``pipeIndex``, ``SegmentResult.index``, ``FittingResult.index`` and a
flag's ``segmentIndex`` / ``fittingIndex`` details.
"""


def pipe_name(index: int) -> str:
    """'pipe 1' for the connection's first pipe segment (index 0), in a sentence."""
    return f"pipe {index + 1}"


def fitting_name(index: int) -> str:
    """'fitting 1' for the connection's first fitting (index 0), in a sentence."""
    return f"fitting {index + 1}"


def pipe_label(index: int) -> str:
    """'Pipe 1': pipe_name() at the start of a label."""
    return pipe_name(index).capitalize()


def fitting_label(index: int) -> str:
    """'Fitting 1': fitting_name() at the start of a label."""
    return fitting_name(index).capitalize()


def fitting_position(pipe_index: int, reducer: bool) -> str:
    """Where a fitting sits, as the piping editor says it: 'pipe 2', or for a reducer (between
    pipeIndex and pipeIndex + 1) 'between pipes 2 and 3'."""
    if reducer:
        return f"between pipes {pipe_index + 1} and {pipe_index + 2}"
    return f"pipe {pipe_index + 1}"
