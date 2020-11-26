from dataclasses import dataclass, field


@dataclass
class ProjectManagerMock:
    projects_list: dict = field(default_factory=dict, init=False)

    def get(self, p_id, **_):
        return self.projects_list[p_id]

    def mock_add_project(self, project):
        self.projects_list[project.id] = project


@dataclass
class GitlabMock:
    projects: ProjectManagerMock = field(default_factory=ProjectManagerMock, init=False)


@dataclass
class GitlabManagerMock:
    gitlab: GitlabMock = field(default_factory=GitlabMock, init=False)
