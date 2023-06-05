#! /usr/bin/env python3
#
# Play with argparse subparsers
#
# Oct-2022, Pat Welch, pat@mousebrains.com

from argparse import ArgumentParser
import logging
import yaml
import json
import datetime
import re
import math
from requests import Session
from tempfile import NamedTemporaryFile
from pathlib import Path

import convert as conv
from loggers import mkLogger, loggerAddArgs, logRequest


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

    def __mkfn(self, fn:str) -> Path:
        return Path(self.__directory, fn + ".yaml").expanduser().absolute() 

    def loadProject(self, project:str) -> dict:
        return self.load("project." + project)

    def saveProject(self, project:str, info) -> dict:
        return self.save("project." + project, info)

    def loadProfiles(self, project:str) -> dict:
        return self.load("profiles." + project)

    def saveProfiles(self, project:str, info) -> dict:
        return self.save("profiles." + project, info)
    
    def loadHistory(self, project:str) -> dict:
        return self.load("history." + project)

    def saveHistory(self, project:str, info) -> dict:
        return self.save("history." + project, info)

    def unlinkProject(self, project:str) -> None:
        fn = self.__mkfn("project." + project)
        if fn.is_file():
            logging.info("Removing %s", fn)
            fn.unlink()

    def save(self, fn:str, info) -> dict:
        fn = self.__mkfn(fn)
        dirname = fn.parent

        if not dirname.exists():
            logging.info("Creating %s", dirname)
            fn.mkdir(parents=True, exist_ok=True) # exist_ok for race conditions
            fn.chmod(0o700) # Make readable only by this user

        tfn = None
        try:
            # Use a temporary file so we'll do an atomic file operation in the move later
            with NamedTemporaryFile(mode="w", dir=dirname, delete=False) as fp:
                tfn = Path(fp.name)
                fp.write("# Created ")
                fp.write("{}".format(datetime.datetime.now()))
                fp.write("\n")
                fp.write(json.dumps(info, sort_keys=True, indent=4))
            tfn.rename(fn) # An atomic rename within same file system
        except:
            logging.exception("Unable to write to %s", fn)
            if tfn: tfn.unlink()

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
            grp.add_argument("--projectProfiles", type=str, default="Project/Profiles",
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
        logRequest(req)
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
            project_name = item["name"]
            items[project_name] = item
            logging.info("Project %s", json.dumps(item, sort_keys=True, indent=4))
            config.saveProject(project_name, item)

            print(project_name)

        return items

class ProjectProfiles:
    def __init__(self, args:ArgumentParser, qFetch:bool=True) -> None:
        self.__args = args
        if qFetch:
            config = Config(args) # For where to save files
            login = Login(args) # Get username/password information
            with Session() as s:
                self.execute(args.project, args, s, config, login)

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to list profiles for")

    def execute(self, project:str, args:ArgumentParser,
                s:Session, config:Config, login:Login) -> dict:
        args = self.__args
        projToken = Projects(args, s).token(project)
        if projToken is None: return None
        url = RAPI.mkURL(args, args.projectProfiles)
        token = login.token(s)
        payload = {"projectToken": projToken}
        hdrs = RAPI.mkHeaders(token)
        req = s.get(url, headers=hdrs, params=payload)
        logRequest(req)
        info = RAPI.checkResponse(req)
        if info is None: return None
        if "body" not in info:
            logging.warning("No body returned for ProjectProfiles\n%s",
                            json.dumps(info, sort_keys=True, indent=4))
            return None
        body = info["body"]
        if not body:
            logging.info("No entries returned for ProjectProfiles\n%s",
                            json.dumps(info, sort_keys=True, indent=4))
            return None
        items = {}
        for item in body:
            print(item["name"])
            items[item["name"]] = item
            logging.info("Profile %s", json.dumps(item, sort_keys=True, indent=4))
        config.saveProfiles(project, items)
        return items

class Projects:
    def __init__(self, args:ArgumentParser, s:Session) -> None:
        self.__args = args
        self.__s = s
        self.__info = {}
        self.__profiles = {}
        self.__qFetch = True

    def  __getitem__(self, project:str) -> dict:
        if project in self.__info:
            return self.__info[project]

        args = self.__args
        config = Config(args) # For where to load files from
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

    def profiles(self, project:str) -> tuple:
        token = self.token(project)
        if not token: return (None, None)
        if project in self.__profiles: return (token, self.__profiles[project])
        args = self.__args
        config = Config(args) # For where to load files from
        login = Login(args) # Get username/password information
        self.__profiles[project] = ProjectProfiles(args, qFetch=False).execute(
                project, args, self.__s, config, login)
        if project in self.__profiles: return (token, self.__profiles[project])
        return (None, None)

class ProjectEdit:
    def __init__(self, args:ArgumentParser) -> None:
        payload =  {}
        if args.name: payload["name"] = args.name
        if args.description: payload["description"] = args.description
        if args.instrument:
            payload["Instruments"] = []
            for sn in args.instrument:
                payload["Instruments"].append({"InstrumentSN": f"SN{sn}"})

        if not payload:
            logging.warning("Nothing to edit for %s", args.project)
            return

        config = Config(args) # Where config files are located
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.projectEdit)
        with Session() as s:
            projectToken = Projects(args, s).token(args.project)
            if not projectToken: return
            hdrs = RAPI.mkHeaders(login.token(s))
            payload["token"] = projectToken
            logging.debug("HEADERS\n%s", json.dumps(hdrs, sort_keys=True, indent=4))
            logging.debug("PAYLOAD\n%s", json.dumps(payload, sort_keys=True, indent=4))
            req = s.post(url, headers=hdrs, json=payload)
            logRequest(req)
            info = RAPI.checkResponse(req)
            if info is None: return
            logging.info("INFO\n%s", json.dumps(info, sort_keys=True, indent=4))

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to create")
        parser.add_argument("--name", type=str, help="New project name")
        parser.add_argument("--description", type=str, help="Project description")
        parser.add_argument("--instrument", type=int, action="append",
                            help="Instrument serial number(s) assigned to the project")

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
        ProjectProfiles.addArgs(a.add_parser("profiles",
                                           description="List profiles in a project",
                                           help="List profiles for a project in the Rockland Cloud",
                                           ))

class Upload:
    def __init__(self, args:ArgumentParser) -> None:
        files = [
                ("", ("file", open(args.filename, "rb"), "application/octet-stream")),
                ("FileType", (None, args.filetype, "text/plain")),
                ]

        config = Config(args) # Where config files are located

        hist = config.loadHistory(args.project)
        if not hist:
            hist = {}

        file = Path(args.filename)
        # If file is already uploaded, do not upload again.
        if file.name in hist:
            return
        
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.profileNew)

        with Session() as s:
            prj = Projects(args, s).token(args.project)
            if not prj: return

            hdrs = RAPI.mkHeaders(login.token(s))
            del hdrs["Content-Type"]

            logging.info("Headers\n%s", json.dumps(hdrs, sort_keys=True, indent=4))
            files.append(("ProjectToken", (None, prj, "text/plain")))
            logging.info("%s", files)
            logging.info("url %s", url)
            req = s.post(url, headers=hdrs, files=files)
            logRequest(req)
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
        config = Config(args) # Where config files are located
        login = Login(args) # Get username/password information
        url = RAPI.mkURL(args, args.dataGet)

        with Session() as s:
            prj = Projects(args, s)
            (token, profiles) = prj.profiles(args.project)
            if not token: return

            _, id2var = conv.load_variable_info(args.metadata_file)
            all_ids = [str(key) for key in id2var]

            params = {
                    "projectToken": token,
                    "DataTypeIds": all_ids,  # Need to be strings!
                    "profileTokens": [],
                    }

            for key in profiles:
                profile = profiles[key]
                logging.info("profile %s", profile)
                params["profileTokens"].append(profile["token"])

            params["profileTokens"] = ",".join(params["profileTokens"])
            params["DataTypeIds"] = ",".join(params["DataTypeIds"])

            hdrs = RAPI.mkHeaders(login.token(s))
            logging.info("Headers\n%s", json.dumps(hdrs, sort_keys=True, indent=4))
            logging.info("Params\n%s", json.dumps(params, sort_keys=True, indent=4))
            logging.info("url %s", url)
            # url = "http://unms.mousebrains.com:4444/api/Data/Get"
            req = s.get(url, headers=hdrs, params=params)
            logRequest(req)

            info = RAPI.checkResponse(req)
            if info is None: return
            logging.info("INFO\n%s", json.dumps(info, sort_keys=True, indent=4))

            with open("info.json", "w") as f: ### <<--- for debugging purpose, delete eventually
                f.write(json.dumps(info, sort_keys=True, indent=4))

            save_dir = Path(args.directory)
            if not save_dir.exists():
                logging.info("Creating output directory %s", save_dir)
                save_dir.mkdir(parents=True)

            # Loop over and save profiles
            for i, key in enumerate(profiles):
                filename = profiles[key]["name"]
                nc_path = Path(save_dir, filename + ".nc")
                logging.info("Saving profile to %s", nc_path)

                ds = conv.profile_to_xrDataset(info["body"][i], args.metadata_file)
                ds.to_netcdf(nc_path)

    @staticmethod
    def addArgs(parser:ArgumentParser) -> None:
        parser.add_argument("project", type=str, help="Project name to store data for")
        parser.add_argument("--directory", type=str, default="result",
                            help="Where to save downloaded files to")
        parser.add_argument("--metadata-file", type=str, default="variable_info.yml",
                            help="File specifying variable names, type IDs, and netCDF metadata")

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
