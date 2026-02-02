class ScraperError(Exception):
    pass


class NetworkError(ScraperError):
    pass


class ParseError(ScraperError):
    pass
