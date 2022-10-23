#! /usr/bin/env python3
#
# Play with argparse subparsers
#
# Oct-2022, Pat Welch, pat@mousebrains.com

from argparse import ArgumentParser
import logging
import logging.handlers
import socket
import getpass
import yaml
import json
import datetime
import time
import re
import math
from requests import Session
from codecs import encode
from tempfile import NamedTemporaryFile
import os
import sys

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

class Config:
    __argsInitialized = False

    def __init__(self, args:ArgumentParser) -> None:
        self.__directory = args.configDirectory

    @classmethod
    def addArgs(cls, parser:ArgumentParser) -> ArgumentParser:
        if not cls.__argsInitialized:
            parser.add_argument("--configDirectory", type=str, default="~/.config/Rockland",
                                help="Where to store configuration files")
            cls.__argsInitialized = True
        return parser

    def __mkfn(self, fn:str) -> str:
        return os.path.abspath(os.path.expanduser(os.path.join(self.__directory, fn + ".yaml")))

    def loadProject(self, project:str) -> dict:
        return self.load("project." + project)

    def saveProject(self, project:str, info) -> dict:
        return self.save("project." + project, info)

    def unlinkProject(self, project:str) -> None:
        fn = self.__mkfn("project." + project)
        if os.path.isfile(fn):
            logging.info("Removing %s", fn)
            os.unlink(fn)

    def save(self, fn:str, info) -> dict:
        fn = self.__mkfn(fn)
        dirname = os.path.dirname(fn)

        if not os.path.isdir(dirname):
            logging.info("Creating %s", dirname)
            os.makedirs(dirname, exist_ok=True) # exist_ok for race conditions
            os.chmod(dirname, 0o700) # Make readable only by this user

        tfn = None
        try:
            # Use a temporary file so we'll do an atomic file operation in the move later
            with NamedTemporaryFile(mode="w", dir=dirname, delete=False) as fp:
                tfn = fp.name
                fp.write("# Created ")
                fp.write("{}".format(datetime.datetime.now()))
                fp.write("\n")
                fp.write(json.dumps(info, sort_keys=True, indent=4))
            os.rename(tfn, fn) # An atomic rename within same file system
        except:
            logging.exception("Unable to write to %s", fn)
            if tfn: os.unlink(tfn)

        return info

    def load(self, fn:str): # Return list or dict
        fn = self.__mkfn(fn)
        try:
            with open(fn, "r") as fp:
                return yaml.safe_load(fp)
        except:
            return None

class RAPI:
    ''' Rockland Cloud API utilities '''

    __initialized = False

    @classmethod
    def addArgs(cls, parser:ArgumentParser) -> ArgumentParser:
        if not cls.__initialized:
            grp = parser.add_argument_group(description="Rockland Cloud API options")
            grp.add_argument("--hostname", type=str,
                             default="https://rocklandapi.azurewebsites.net",
                             help="Hostname to connecto to")
            grp.add_argument("--sourceToken", type=str, default="c6X2ADq9YqA3Hh5",
                             help="Login Source Token to specify which app to connect to")
            grp.add_argument("--login", type=str, default="Auth/Login",
                             help="Authentication path")
            grp.add_argument("--profileNew", type=str, default="Profile/New",
                             help="Put new data profile")
            grp.add_argument("--dataGet", type=str, default="Data/Get",
                             help="Fetch data")
            grp.add_argument("--projectCreate", type=str, default="Project/Create",
                             help="Create a project")
            grp.add_argument("--projectList", type=str, default="Project/List",
                             help="Project list path")
            grp.add_argument("--projectProfile", type=str, default="Project/Profile",
                             help="Project list profiles path")
            grp.add_argument("--projectEdit", type=str, default="Project/Edit",
                             help="Project edit path")
            grp.add_argument("--projectDelete", type=str, default="Project/Delete",
                             help="Project Delete path")
            cls.__initialized = True
        return parser

    @staticmethod
    def mkURL(args:ArgumentParser, path:str) -> str:
        return f"{args.hostname}/api/{path}"

    @staticmethod
    def mkHeaders(authToken:str=None) -> dict:
        hdr = {"Content-Type": "application/json"}
        if authToken:
            hdr["Authorization"] = "Bearer " + authToken
        return hdr

    @staticmethod
    def checkResponse(req) -> dict:
        if req.ok: return req.json()
        logging.error("Fetching %s", req.url)
        logging.error("Code %s -> Reason %s", req.status_code, req.reason)
        if req.text:
            info = req.json()
            if info:
                logging.error("\n%s", json.dumps(info, sort_keys=True, indent=4))
            else:
                logging.error("\n%s", req.text)
        return None

    @staticmethod
    def parseTimestamp(ts:str) -> float:
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})[.](\d+)Z", ts)
        if not match:
            logging.warning("Error parsing %s", ts)
            return None

        frac = float(match[7]) / math.pow(10, len(match[7]))
        try:
            t = datetime.datetime(
                    int(match[1]), # year
                    int(match[2]), # month
                    int(match[3]), # day of month
                    int(match[4]), # hours
                    int(match[5]), # minutes
                    int(match[6]), # seconds
                    int(round(frac * 1e6)), # microseconds
                    datetime.timezone.utc)
            return t
        except:
            logging.exception("Parsing %s", ts)
            return None

class Credentials:
    def __init__(self, args:ArgumentParser) -> None:
        prompts = (
                ("username", "username"),
                ("password", "password"),
                ("OrganizationName", "organization name"),
                )

        config = Config(args)
        fn = args.credentials

        try:
            self.__info = self.__load(fn, config, prompts)
        except:
            self.__info = self.__save(fn, config, prompts, args.sourceToken)

    def __repr__(self) -> str:
        return self.payload()

    @staticmethod
    def addArgs(parser:ArgumentParser) -> ArgumentParser:
        Config.addArgs(parser)
        grp = parser.add_argument_group(description="Credential related options")
        grp.add_argument("--credentials", type=str, default="credentials",
                         help="Filename containing credentials for the Rockland cloud connection")
        return parser

    def payload(self) -> str:
        return self.__info
        # return json.dumps(self.__info, sort_keys=True, indent=4)

    def __load(self, fn:str, config:Config, prompts:tuple[tuple[str,str]]) -> dict:
        info = config.load(fn)
        if not info: raise FileNotFoundError(fn)
        logging.debug("Info %s", info)
        for (key, prompt) in prompts:
            if key not in info:
                logging.error("%s not found in %s, %s", key, fn, prompt)
                raise ValueError
        return info

    def __save(self, fn:str, config:Config, prompts:tuple[tuple[str,str]], srcToken:str) -> dict:
        info = {"sourceToken": srcToken}
        for (key, prompt) in prompts:
            info[key] = input(f"Rockland Cloud {prompt}: ").strip()
            if not info[key]: raise Exception(f"{key} is empty")

        return config.save(fn, info)

class Login:
    def __init__(self, args:ArgumentParser) -> None:
        self.__args = args
        self.__token = None
        self.__expiry = None
        self.__payload = Credentials(args).payload()
        self.__url = RAPI.mkURL(args, args.login)
        self.__headers = RAPI.mkHeaders()
        self.__filename = "authentication"
        self.__config = Config(args)
        try:
            info = self.__config.load(self.__filename)
            if "token" in info and "expiry" in info:
                self.__token = info["token"]
                self.__expiry = datetime.datetime.fromisoformat(info["expiry"])
        except:
            pass

    @staticmethod
    def addArgs(parser:ArgumentParser) -> ArgumentParser:
        RAPI.addArgs(parser)
        Credentials.addArgs(parser)
        return parser

    def token(self, s:Session) -> str:
        if self.__expiry is not None:
            now = datetime.datetime.now(tz=datetime.timezone.utc) 
            threshold = now - datetime.timedelta(seconds=1) # Renew if within 1 second
            if self.__expiry > threshold: 
                return self.__token

        # No token or expired, so fetch a new one
        req = s.post(self.__url, headers=self.__headers, json=self.__payload)
        info = RAPI.checkResponse(req)
        if info is None: return None
        logging.info("Reply JSON\n%s", json.dumps(info, sort_keys=True, indent=4))
        body = info["body"]
        logging.info("Body\n%s", json.dumps(body, sort_keys=True, indent=4))
        self.__token = body["token"]
        self.__expiry = RAPI.parseTimestamp(body["tokenExpiry"])
        logging.info("token '%s' expiry %s", self.__token, self.__expiry)
        self.__config.save(self.__filename, {
            "token": self.__token,
            "expiry": self.__expiry.isoformat()})
        return self.__token

class ProjectCreate:
    def __init__(self, args:ArgumentParser) -> None:
        payload = {
                "Name": args.project,
                "Description": args.description,
                "DataType": "RDL_isdp",
                "Instruments": [],
                }
        for sn in args.sn:
            payload["Instruments"].append({"InstrumentSN": f"{sn}"})

        config = Config(args) # Where configuration files are stored
        login = Login(args) # Get authentication token
        url = RAPI.mkURL(args, args.projectCreate)
        with Session() as s:
            token = login.token(s)
            hdrs = RAPI.mkHeaders(token)
            logging.debug("HEADERS\n%s", json.dumps(hdrs, sort_keys=True, indent=4))
            logging.debug("PAYLOAD\n%s", payload)
            req = s.post(url, headers=hdrs, json=payload)
            info = RAPI.checkResponse(req)
            if info is None: return
            logging.info("INFO\n%s", json.dumps(info, sort_keys=True, indent=4))
            prj = { # Translate case
                    "dataType": payload["DataType"],
                    "description": payload["Description"],
                    "instruments": payload["Instruments"],
                    "name": payload["Name"],
                    "token": info["body"],
                    }
            logging.info("Project\n%s", json.dumps(prj, sort_keys=True, indent=4))
            config.saveProject(prj["name"], prj)

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to create")
        parser.add_argument("description", type=str, help="Project description")
        parser.add_argument("sn", type=int, nargs="+", help="Instrument serial numbers")

class ProjectList:
    def __init__(self, args:ArgumentParser, qFetch:bool=True) -> None:
        self.__args = args
        if qFetch:
            config = Config(args) # For where to save files
            login = Login(args) # Get username/password information
            with Session() as s:
                self.execute(args, s, config, login)

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("--save", action="store_true", help="Save project information locally")

    def execute(self, args:ArgumentParser, s:Session, config:Config, login:Login) -> dict:
        url = RAPI.mkURL(args, args.projectList)
        token = login.token(s)
        hdrs = RAPI.mkHeaders(token)
        req = s.get(url, headers=hdrs)
        info = RAPI.checkResponse(req)
        if info is None: return None
        if "body" not in info:
            logging.warning("No body returned for ProjectList\n%s",
                            json.dumps(info, sort_keys=True, indent=4))
            return None
        body = info["body"]
        if not body:
            logging.info("No entries returned for ProjectList\n%s",
                            json.dumps(info, sort_keys=True, indent=4))
            return None
        items = {}
        for item in body:
            items[item["name"]] = item
            logging.info("Project %s", json.dumps(item, sort_keys=True, indent=4))
            config.saveProject(item["name"], item)
        return items

class Projects:
    def __init__(self, args:ArgumentParser, s:Session) -> None:
        self.__args = args
        self.__s = s
        self.__info = {}
        self.__qFetch = True

    def  __getitem__(self, project:str) -> dict:
        if project in self.__info:
            return self.__info[project]

        args = self.__arga
        config = Config(args) # For where to save files
        info = config.loadProject(project)
        if info:
            self.__info[project] = info
            return info
       
        if self.__qFetch:
            login = Login(args) # Get username/password information
            items = ProjectList(args, qFetch=False).execute(args, self.__s, config, login)
            self.__info = items if items else {}
            self.__qFetch = False
        
        if project in self.__info:
            return self.__info[project]

        logging.warning("Unknown project %s", project)
        return None

    def token(self, project:str) -> str:
        info = self[project]
        return info["token"] if info and "token" in info else None

class ProjectProfile:
    def __init__(self, args:ArgumentParser, qFetch:bool=True) -> None:
        self.__args = args
        if qFetch:
            config = Config(args) # For where to save files
            login = Login(args) # Get username/password information
            with Session() as s:
                self.execute(args, s, config, login)

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("--save", action="store_true",
                            help="Save project profile information locally")

    def execute(self, args:ArgumentParser, s:Session, config:Config, login:Login) -> dict:
        url = RAPI.mkURL(args, args.projectProfile)
        token = login.token(s)
        hdrs = RAPI.mkHeaders(token)
        req = s.get(url, headers=hdrs)
        info = RAPI.checkResponse(req)
        if info is None: return None
        if "body" not in info:
            logging.warning("No body returned for ProjectList\n%s",
                            json.dumps(info, sort_keys=True, indent=4))
            return None
        body = info["body"]
        if not body:
            logging.info("No entries returned for ProjectList\n%s",
                            json.dumps(info, sort_keys=True, indent=4))
            return None
        items = {}
        for item in body:
            items[item["name"]] = item
            logging.info("Project %s", json.dumps(item, sort_keys=True, indent=4))
            config.saveProfile(item["name"], item)
        return items

class ProjectEdit:
    def __init__(self, args:ArgumentParser) -> None:
        config = Config(args) # Where config files are located
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.projectEdit)
        with Session() as s:
            projectToken = Projects(args, s).token(args.project)
            if not projectToken: return
            hdrs = RAPI.mkHeaders(login.token(s))
            payload = { "Name": args.project, "projectToken": projectToken, }
            if args.description:
                payload["Description"] = args.description
            if args.add:
                payload["Instruments"] = []
                for sn in args.add:
                    payload["Instruments"].append({"InstrumentSN": f"SN{sn}"})
            if args.delete:
                logging.warning("--delete not yet implemented!")
                sys.exit(1)
            logging.debug("HEADERS\n%s", json.dumps(hdrs, sort_keys=True, indent=4))
            logging.debug("PAYLOAD\n%s", json.dumps(payload, sort_keys=True, indent=4))
            req = s.post(url, headers=hdrs, json=payload)
            logging.info("COOKIES %s", req.cookies)
            logging.info("ELAPSED %s", req.elapsed)
            logging.info("encoding %s", req.encoding)
            logging.info("headers\n%s", json.dumps(dict(req.headers), sort_keys=True, indent=4))
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
            info = RAPI.checkResponse(req)
            if info is None: return
            logging.info("INFO\n%s", json.dumps(info, sort_keys=True, indent=4))

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to create")
        parser.add_argument("description", type=str, help="Project description")
        parser.add_argument("sn", type=int, nargs="+", help="Instrument serial numbers")

class ProjectList:
    def __init__(self, args:ArgumentParser) -> None:
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.projectList)
        with Session() as s:
            token = login.token(s)
            hdrs = RAPI.mkHeaders(token)
            req = s.request("GET", url, headers=hdrs)
            info = RAPI.checkResponse(req)
            if info is None: return
            if "body" not in info:
                logging.warning("No body returned for ProjectList\n%s",
                                json.dumps(info, sort_keys=True, indent=4))
                return
            body = info["body"]
            if not body:
                logging.warning("No entries returned for ProjectList\n%s",
                                json.dumps(info, sort_keys=True, indent=4))
                return
            for item in body:
                logging.info("Project %s", json.dumps(item, sort_keys=True, indent=4))

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("--save", action="store_true", help="Save project information locally")

class ProjectEdit:
    def __init__(self, args:ArgumentParser) -> None:
        self.__args = args

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to edit")
        parser.add_argument("--description", type=str, help="Project description")
        parser.add_argument("--add", type=int, action="append",
                            help="Instrument serial numbers append")
        parser.add_argument("--delete", type=int, action="append",
                            help="Instrument serial numbers to remove")

class ProjectDelete:
    def __init__(self, args:ArgumentParser) -> None:
        config = Config(args) # Where config files are located
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.projectDelete)
        with Session() as s:
            projects = Projects(args, s)
            for name in args.project:
                token = projects.token(name)
                if token:
                    self.remove(name, token, s, url, config, login)

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, nargs="+", help="Project name(s) to delete")

    def remove(self, name:str, projectToken:str, s:Session, 
               url:str, config:Config, login:Login) -> None:
        token = login.token(s)
        hdrs = RAPI.mkHeaders(token)
        payload = { "projectToken": projectToken, }
        logging.info("Headers %s", hdrs)
        logging.info("Payload %s", payload)
        req = s.post(url, headers=hdrs, params=payload)
        info = RAPI.checkResponse(req)
        if info is None: return
        config.unlinkProject(prj["name"])
        logging.info("Removed %s", name)

class Project:
    def __init__(self, args:ArgumentParser) -> None:
        mapping = {
                "create": ProjectCreate,
                "list": ProjectList,
                "edit": ProjectEdit,
                "delete": ProjectDelete,
                "profiles": ProjectProfiles,
                }
        logging.info("cmd %s mapping %s", args.cmdProject, mapping[args.cmdProject](args))

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        a = parser.add_subparsers(
                title="Project API commands",
                description="Rockland Cloud Project API commands",
                dest="cmdProject",
                required=True,
                help="Commands to work on projects",
                metavar="command",
                )
        ProjectCreate.addArgs(a.add_parser("create",
                                           description="Create a project",
                                           help="Create a project in the Rockland Cloud",
                                           ))
        ProjectList.addArgs(a.add_parser("list",
                                         description="List projects",
                                         help="List projects in the Rockland Cloud",
                                         ))
        ProjectEdit.addArgs(a.add_parser("edit",
                                         description="Edit projects",
                                         help="Edit projects in the Rockland Cloud",
                                         ))
        ProjectDelete.addArgs(a.add_parser("delete",
                                           description="Delete a project",
                                           help="Delete a project in the Rockland Cloud",
                                           ))

class Upload:
    def __init__(self, args:ArgumentParser) -> None:
        files = [
                ("", ("file", open(args.filename, "rb"), "application/octet-stream")),
                ("FileType", (None, args.filetype, "text/plain")),
                ]
 
        config = Config(args) # Where config files are located
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.profileNew)

        with Session() as s:
            prj = config.loadProject(args.project)
            if prj is None:
                items = ProjectList(args, qFetch=False).execute(args, s, config, login)
                if not prj or args.project not in prj:
                    logging.warning("Unknown project, %s", args.project)
                    sys.exit(1)
                prj = items[args.project]
            hdrs = RAPI.mkHeaders(login.token(s))
            del hdrs["Content-Type"]

            logging.info("Headers\n%s", json.dumps(hdrs, sort_keys=True, indent=4))
            files.append(("ProjectToken", (None, prj["token"], "text/plain")))
            logging.info("%s", files)
            logging.info("url %s", url)
            req = s.post(url, headers=hdrs, files=files)
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
            info = RAPI.checkResponse(req)
            if info is None: return
            logging.info("INFO\n%s", json.dumps(info, sort_keys=True, indent=4))

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to store data for")
        parser.add_argument("filename", type=str, help="file to upload")
        parser.add_argument("--filetype", type=str, default="RDL_isdp",
                            help="filetype being uploaded")

class Download:
    def __init__(self, args:ArgumentParser) -> None:
        pass

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        pass
        # parser.add_argument("project", type=str, help="Project name to store data for")
        # parser.add_argument("qfile", type=str, help="q-file to upload")

def main():
    parser = ArgumentParser(description="Rockland Cloud API")
    loggerAddArgs(parser)
    Login.addArgs(parser)
    subParsers = parser.add_subparsers(
            title="Rockland Cloud API commands",
            description="Rockland Cloud project commands",
            dest="cmd",
            required=True,
            help="Project related help",
            metavar="command")
    Project.addArgs(subParsers.add_parser("project",
                                          aliases=("prj",),
                                          description="Project related commands",
                                          help="Project related commands"))

    Upload.addArgs(subParsers.add_parser("upload",
                                      aliases=("send",),
                                      description="Upload profile(s)",
                                      help="Upload profile(s)"))
    Download.addArgs(subParsers.add_parser("download",
                                      aliases=("get",),
                                      description="Download profile(s)",
                                      help="Download profile(s)"))
    args = parser.parse_args()

    mkLogger(args, fmt="%(asctime)s %(levelname)s: %(message)s")

    logging.info("Args %s", args)

    mapping = {
            "project": Project,
            "prj": Project,
            "upload": Upload,
            "send": Upload,
            "download": Download,
            "get": Download,
            }

    mapping[args.cmd](args)

if __name__ == "__main__":
    main()
