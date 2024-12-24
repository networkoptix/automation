## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from typing import Optional

from pydantic import BaseModel, Field

# Refer to the Pydantic documentation for information about how to extend and modify the
# configuration schema: https://docs.pydantic.dev/2.4/.
# Note that certain fields may not exist in all repo configurations, so use Optional[] where
# appropriate.


class JiraConfig(BaseModel):
    url: str = Field(description="URL to the JIRA instance.")
    login: str = Field(description="Username for API requests.")
    password: str = Field(description="Password or token for API requests.")
    timeout: int = Field(
        description="Timeout (in seconds) for API requests.", default=10)
    retries: int = Field(description="Number of retries for API requests.", default=3)
    project_keys: Optional[list[str]] = Field(
        description=(
            "List of JIRA project keys to work with. Deprecated - use project_mapping instead."),
        default=[])
    project_mapping: Optional[dict[str, str]] = Field(
        description="Default GitLab Projects for supported Jira Projects.", default={})


class RepoConfig(BaseModel):
    path: str = Field(description="Path where the repository should be cloned to.")
    url: str = Field(description="Git URL to the repository.")
    need_code_owner_approval: Optional[bool] = Field(
        description="If code owner approval is needed for merging.", default=False)


class ApprovalRuleConfig(BaseModel):
    patterns: list[str] = Field(
        description="List of path patterns where this rule applies.")
    approvers: list[str] = Field(
        description="List of gitlab usernames that are allowed to approve.")


class ApproveRulesetConfig(BaseModel):
    relevance_checker: str = Field(
        description="Name of a function that decides if the rule is relevant.")
    rules: list[ApprovalRuleConfig] = Field(description="List of approval rules.")


class ApproveRulesetEntryConfig(BaseModel):
    approve_ruleset: ApproveRulesetConfig = Field(description="The approval ruleset.")


class CommonRuleConfig(BaseModel):
    excluded_issue_title_patterns: Optional[list[str]] = Field(
        description="List of regular expressions that are checked against the MR title. When "
        "at least one expression is matching, the rule is skipped.",
        default=None)


class JobStatusCheckRuleConfig(CommonRuleConfig):
    open_source: ApproveRulesetEntryConfig = Field(
        description="The approval ruleset for open source.")
    apidoc: Optional[ApproveRulesetEntryConfig] = Field(
        description="The approval ruleset for apidoc changes.", default=None)
    code_owner_approval: Optional[ApproveRulesetEntryConfig] = Field(
        description="The approval ruleset for checking changes by code owners.", default=None)


class RelatedMergeRequestRuleConfig(CommonRuleConfig):
    trigger_title_pattern: str = Field(
        description="Regex for detecting issues in the base project to trigger this rule.")
    issue_keys_pattern: str = Field(
        description="Regex for finding related issues in the issue text.")
    related_projects: list[str] = Field(
        description="List of related JIRA projects.")
    action: str


class ProcessRelatedMergeRequestRuleConfig(BaseModel):
    rules: list[RelatedMergeRequestRuleConfig] = Field(
        description="List of rules for processing related Merge Requests.")


class NxSubmoduleCheckRuleConfig(CommonRuleConfig):
    nx_submodule_dirs: list[str] = Field(
        description="List of directories that are considered Nx Submodules.")


class PipelineConfig(BaseModel):
    autorun_stage: Optional[str] = Field(
        description="Name of the stage that should trigger the pipeline to run automatically.",
        default=None)


class FollowUpRuleConfig(CommonRuleConfig):
    pass


class EssentialRuleConfig(CommonRuleConfig):
    pass


class WorkflowCheckRuleConfig(CommonRuleConfig):
    pass


class CommitMessageRuleConfig(CommonRuleConfig):
    pass


class Config(BaseModel):
    jira: JiraConfig
    repo: RepoConfig
    pipeline: Optional[PipelineConfig] = None
    enabled_rules: Optional[list[str]] = None
    job_status_check_rule: Optional[JobStatusCheckRuleConfig] = None
    process_related_merge_requests_rule: Optional[ProcessRelatedMergeRequestRuleConfig] = None
    nx_submodule_check_rule: Optional[NxSubmoduleCheckRuleConfig] = None
    follow_up_rule: Optional[FollowUpRuleConfig] = None
    essential_check_rule: Optional[EssentialRuleConfig] = None
    workflow_check_rule: Optional[WorkflowCheckRuleConfig] = None
    commit_message_check_rule: Optional[CommitMessageRuleConfig] = None
