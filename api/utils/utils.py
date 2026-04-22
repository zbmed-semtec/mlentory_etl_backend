from rdflib.util import from_n3

class Utils:
    """
    Utility class for common functions.
    """
    
    MLENTORY_GRAPH = "https://w3id.org/mlentory"

    @staticmethod
    def n3_to_term(n3: str) -> str:
        """
        Converts an N3 formatted string to a term.
        """
        return from_n3(n3.encode("unicode_escape").decode("unicode_escape"))