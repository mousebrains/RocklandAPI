from argparse import ArgumentParser
import logging
import logging.handlers
import socket
import getpass


# This is from TPWUtils/Logger.py
#
# Set up logging to rolling files and/or SMTP
#
def loggerAddArgs(parser:ArgumentParser) -> None:
    ''' Add command line arguments I will use '''
    grp = parser.add_argument_group("Logger Related Options")
    grp.add_argument("--logfile", type=str, metavar="filename", help="Name of logfile")
    grp.add_argument("--logBytes", type=int, default=10000000, metavar="length",
            help="Maximum logfile size in bytes")
    grp.add_argument("--logCount", type=int, default=3, metavar="count",
            help="Number of backup files to keep")
    grp.add_argument("--mailTo", action="append", metavar="foo@bar.com",
            help="Where to mail errors and exceptions to")
    grp.add_argument("--mailFrom", type=str, metavar="foo@bar.com",
            help="Who the mail originates from")
    grp.add_argument("--mailSubject", type=str, metavar="subject",
            help="Mail subject line")
    grp.add_argument("--smtpHost", type=str, default="localhost", metavar="foo.bar.com",
            help="SMTP server to mail to")
    gg = grp.add_mutually_exclusive_group()
    gg.add_argument("--debug", action="store_true", help="Enable very verbose logging")
    gg.add_argument("--verbose", action="store_true", help="Enable verbose logging")


def mkLogger(args:ArgumentParser,
        fmt:str="%(asctime)s %(threadName)s %(levelname)s: %(message)s",
        name:str=None,
        logLevel:str="WARNING") -> logging.Logger:
    ''' Construct a logger and return it '''
    logger = logging.getLogger(name) # If name is None, then root logger
    logger.handlers.clear() # Clear any pre-existing handlers for name

    if args.logfile:
        ch = logging.handlers.RotatingFileHandler(args.logfile,
                maxBytes=args.logBytes,
                backupCount=args.logCount)
    else:
        ch = logging.StreamHandler()

    logLevel = \
            logging.DEBUG if args.debug else \
            logging.INFO if args.verbose else \
            logLevel
    logger.setLevel(logLevel)
    ch.setLevel(logLevel)

    formatter = logging.Formatter(fmt)
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    if args.mailTo is not None:
        frm = args.mailFrom if args.mailFrom is not None else \
                (getpass.getuser() + "@" + socket.getfqdn())
        subj = args.mailSubject if args.mailSubject is not None else \
                ("Error on " + socket.getfqdn())

        ch = logging.handlers.SMTPHandler(args.smtpHost, frm, args.mailTo, subj)
        ch.setLevel(logging.ERROR)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger


def logRequest(req) -> None:
    logging.info("COOKIES %s", req.cookies)
    logging.info("ELAPSED %s", req.elapsed)
    logging.info("encoding %s", req.encoding)
    logging.info("headers\n%s", req.headers)
    logging.info("history %s", req.history)
    logging.info("is_permanent_redirect %s", req.is_permanent_redirect)
    logging.info("is_redirect %s", req.is_redirect)
    logging.info("links %s", req.links)
    logging.info("next %s", req.next)
    logging.info("ok %s", req.ok)
    logging.info("reason %s", req.reason)
    logging.info("request %s", req.request)
    logging.info("status_code %s", req.status_code)
    logging.info("text %s", req.text)
    logging.info("url %s", req.url)