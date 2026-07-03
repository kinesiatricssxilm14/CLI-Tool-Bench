"""
Data model building for the SuperProductivity-compatible JSON backup format.
"""
from typing import Any, Dict, List, Optional

from .utils import gen_id, now_ms

DEFAULT_PROJECT_ID = "default"
DEFAULT_PROJECT_TITLE = "Imported Tasks"


def _default_theme() -> Dict[str, Any]:
    return {
        "primary": "",
        "huePrimary": "500",
        "accent": "",
        "hueAccent": "A200",
        "warn": "",
        "hueWarn": "A200",
        "backgroundImageDark": None,
        "backgroundImageLight": None,
        "isAutoContrast": True,
        "isDisableBackgroundStyling": False,
    }


def _default_project(project_id: str, title: str) -> Dict[str, Any]:
    return {
        "id": project_id,
        "title": title,
        "taskIds": [],
        "backlogTaskIds": [],
        "isHiddenFromMenu": False,
        "isArchived": False,
        "noteIds": [],
        "breakTime": {},
        "breakNr": {},
        "theme": _default_theme(),
    }


def _default_tag(tag_id: str, title: str) -> Dict[str, Any]:
    return {
        "id": tag_id,
        "title": title,
        "color": None,
        "taskIds": [],
        "icon": None,
    }


def _default_task(
    task_id: str,
    title: str,
    is_done: bool = False,
    notes: str = "",
    project_id: Optional[str] = None,
    tag_ids: Optional[List[str]] = None,
    sub_task_ids: Optional[List[str]] = None,
    time_estimate: int = 0,
    due_day: Optional[str] = None,
    parent_id: Optional[str] = None,
    created: Optional[int] = None,
) -> Dict[str, Any]:
    if tag_ids is None:
        tag_ids = []
    if sub_task_ids is None:
        sub_task_ids = []
    if created is None:
        created = now_ms()
    return {
        "id": task_id,
        "projectId": project_id,
        "tagIds": tag_ids,
        "subTaskIds": sub_task_ids,
        "title": title,
        "isDone": is_done,
        "notes": notes,
        "timeEstimate": time_estimate,
        "timeSpent": 0,
        "created": created,
        "dueDay": due_day,
        "plannedAt": None,
        "_showSubTasksMode": 2,
        "repeatCfgId": None,
        "parentId": parent_id,
        "attachmentIds": [],
        "reminderId": None,
        "issueId": None,
        "issueProviderId": None,
        "issueType": None,
        "issueLastUpdated": None,
        "issueAttachmentNr": None,
        "issueCommentNr": None,
        "isDoneHidden": None,
        "timeSpentOnDay": {},
    }


def _default_global_config() -> Dict[str, Any]:
    return {
        "misc": {
            "firstDayOfWeek": 0,
            "startOfNextDay": 0,
            "taskNotesTpl": None,
            "defaultProjectId": None,
            "isConfirmBeforeDeletingParentWithSubTasks": False,
        },
        "isHideNav": False,
        "isShowLargeNotesOnTaskList": False,
        "isTodayTagEnabled": False,
        "isDisplayTodayRemainingValue": False,
        "isTaskRepeatEnabled": False,
        "evaluation": {},
        "idle": {
            "isOncePerSession": True,
            "isEnableIdleTimeTracking": False,
            "minIdleTime": 300000,
            "resetBreakTimer": True,
            "isUnTrackedIdleResetsBreakTimer": True,
        },
        "pomodoro": {
            "isEnabled": False,
            "duration": 1500000,
            "breakDuration": 300000,
            "longerBreakDuration": 900000,
            "cyclesBeforeLongerBreak": 4,
            "isStopTrackingOnBreak": False,
            "isStopTrackingOnLongBreak": False,
            "isManualContinue": False,
            "isPlaySound": False,
            "isPlaySoundAfterBreak": False,
            "isPlayTick": False,
        },
        "keyboard": {},
        "sound": {
            "volume": 50,
            "isPlayDoneSound": False,
            "doneSound": None,
        },
        "trackingReminder": {
            "isEnabled": False,
            "minTime": 60000,
            "remindAt": None,
        },
        "googleTimeSheetExport": {
            "spreadsheetId": None,
            "isAutoLogin": False,
            "isAutoExportToSheet": False,
            "isRoundWorkTimeUp": None,
            "roundWorkTimeTo": None,
            "sheetId": None,
            "lastExported": None,
        },
        "simpleSummarySettings": {},
    }


def build_empty_data() -> Dict[str, Any]:
    """Build the base JSON data structure with defaults."""
    ts = now_ms()
    default_project = _default_project(DEFAULT_PROJECT_ID, DEFAULT_PROJECT_TITLE)
    return {
        "data": {
            "task": {
                "ids": [],
                "entities": {},
            },
            "project": {
                "ids": [DEFAULT_PROJECT_ID],
                "entities": {
                    DEFAULT_PROJECT_ID: default_project,
                },
            },
            "tag": {
                "ids": [],
                "entities": {},
            },
            "note": {
                "ids": [],
                "entities": {},
            },
            "taskAttachment": {
                "ids": [],
                "entities": {},
            },
            "bookmark": {
                "ids": [],
                "entities": {},
            },
            "metric": {
                "ids": [],
                "entities": {},
            },
            "improvement": {
                "ids": [],
                "entities": {},
            },
            "obstruction": {
                "ids": [],
                "entities": {},
            },
            "reminder": [],
            "globalConfig": _default_global_config(),
            "lastLocalSyncModelChange": ts,
            "archiveOld": {
                "task": {
                    "ids": [],
                    "entities": {},
                },
                "timeTracking": {
                    "project": {},
                    "tag": {},
                },
                "lastTimeTrackingFlush": ts,
            },
        },
        "crossModelVersion": 4.2,
    }


class DataBuilder:
    """Builds the JSON data structure from parsed task specs."""

    def __init__(self, base_data: Optional[Dict[str, Any]] = None):
        if base_data is not None:
            self.data = base_data
        else:
            self.data = build_empty_data()
        # Build reverse lookup: project title -> project id
        self._project_by_name: Dict[str, str] = {}
        for pid, proj in self.data["data"]["project"]["entities"].items():
            self._project_by_name[proj["title"]] = pid
        # Build reverse lookup: tag title -> tag id
        self._tag_by_name: Dict[str, str] = {}
        for tid, tag in self.data["data"]["tag"]["entities"].items():
            self._tag_by_name[tag["title"]] = tid

    def get_or_create_project(self, name: str) -> str:
        """Return project ID for the given name, creating it if needed."""
        if name in self._project_by_name:
            return self._project_by_name[name]
        pid = gen_id()
        project = _default_project(pid, name)
        self.data["data"]["project"]["ids"].append(pid)
        self.data["data"]["project"]["entities"][pid] = project
        self._project_by_name[name] = pid
        return pid

    def get_or_create_tag(self, name: str) -> str:
        """Return tag ID for the given name, creating it if needed."""
        if name in self._tag_by_name:
            return self._tag_by_name[name]
        tid = gen_id()
        tag = _default_tag(tid, name)
        self.data["data"]["tag"]["ids"].append(tid)
        self.data["data"]["tag"]["entities"][tid] = tag
        self._tag_by_name[name] = tid
        return tid

    def add_task(
        self,
        title: str,
        is_done: bool = False,
        notes: str = "",
        project_name: Optional[str] = None,
        tag_names: Optional[List[str]] = None,
        time_estimate: int = 0,
        due_day: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> str:
        """Add a task and return its generated ID."""
        if tag_names is None:
            tag_names = []

        task_id = gen_id()

        # Resolve project
        project_id: Optional[str] = None
        if parent_id is None:
            if project_name:
                project_id = self.get_or_create_project(project_name)
            else:
                project_id = DEFAULT_PROJECT_ID
        # Subtasks do not have a projectId (it's inherited from parent)

        # Resolve tags
        tag_ids = [self.get_or_create_tag(t) for t in tag_names if t]

        task = _default_task(
            task_id=task_id,
            title=title,
            is_done=is_done,
            notes=notes,
            project_id=project_id,
            tag_ids=tag_ids,
            time_estimate=time_estimate,
            due_day=due_day,
            parent_id=parent_id,
        )

        # Register task
        self.data["data"]["task"]["ids"].append(task_id)
        self.data["data"]["task"]["entities"][task_id] = task

        # Add to project's taskIds (only top-level tasks)
        if parent_id is None and project_id is not None:
            self.data["data"]["project"]["entities"][project_id]["taskIds"].append(task_id)

        # Add to each tag's taskIds
        for tid in tag_ids:
            self.data["data"]["tag"]["entities"][tid]["taskIds"].append(task_id)

        return task_id

    def add_subtask_to_parent(self, parent_id: str, subtask_id: str):
        """Register a subtask under a parent task."""
        self.data["data"]["task"]["entities"][parent_id]["subTaskIds"].append(subtask_id)

    def get_task_count(self) -> int:
        return len(self.data["data"]["task"]["ids"])

    def get_project_count(self) -> int:
        return len(self.data["data"]["project"]["ids"])

    def get_tag_count(self) -> int:
        return len(self.data["data"]["tag"]["ids"])

    def get_completed_count(self) -> int:
        return sum(
            1 for t in self.data["data"]["task"]["entities"].values() if t["isDone"]
        )

    def get_incomplete_count(self) -> int:
        return sum(
            1 for t in self.data["data"]["task"]["entities"].values() if not t["isDone"]
        )

    def get_projects_summary(self) -> List[Dict[str, Any]]:
        """Return list of dicts with project name and task count."""
        result = []
        for pid in self.data["data"]["project"]["ids"]:
            proj = self.data["data"]["project"]["entities"][pid]
            result.append({"title": proj["title"], "task_count": len(proj["taskIds"])})
        return result

    def get_tags_summary(self) -> List[Dict[str, Any]]:
        """Return list of dicts with tag name and task count."""
        result = []
        for tid in self.data["data"]["tag"]["ids"]:
            tag = self.data["data"]["tag"]["entities"][tid]
            result.append({"title": tag["title"], "task_count": len(tag["taskIds"])})
        return result
