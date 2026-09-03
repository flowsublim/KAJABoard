from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.projects.forms import (
    ProjectBudgetLineForm,
    ProjectForecastLineForm,
    ProjectForm,
    ProjectReasonForm,
    ProjectSalesOrderLinkForm,
)
from apps.projects.models import ProjectState
from apps.projects.selectors import (
    project_b2b_demand_candidates,
    project_detail,
    project_profitability,
    project_progress,
    projects,
)
from apps.projects.services import (
    activate_project,
    add_project_budget_line,
    add_project_forecast_line,
    cancel_project,
    complete_project,
    create_draft_project,
    hold_project,
    link_sales_order,
    release_project,
    remove_project_forecast_line,
    update_draft_project,
    update_project_forecast_line,
)


def _require(user, permission):
    if not user.has_perm(permission):
        raise PermissionDenied


def _errors(form, error):
    for message in getattr(error, "messages", [str(error)]):
        form.add_error(None, message)


def _values(form):
    fields = {field.name for field in form._meta.model._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in fields}


def _project(user, pk):
    return get_object_or_404(projects(user), pk=pk)


@login_required
def project_list(request):
    _require(request.user, "projects.view_project")
    queryset = projects(
        request.user, search=request.GET.get("q", "").strip(), state=request.GET.get("state", "")
    )
    return render(
        request,
        "projects/project_list.html",
        {
            "page": Paginator(queryset, 25).get_page(request.GET.get("page")),
            "states": ProjectState.choices,
            "can_add": request.user.has_perm("projects.add_project"),
        },
    )


@login_required
def project_create(request):
    _require(request.user, "projects.add_project")
    form = ProjectForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            project = create_draft_project(actor=request.user, **_values(form))
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(request, "projects/project_form.html", {"form": form, "title": "New Project"})


@login_required
def project_detail_view(request, pk):
    _require(request.user, "projects.view_project")
    project = project_detail(request.user, pk=pk)
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "profitability": project_profitability(project),
            "progress": project_progress(project),
            "demand_candidates": project_b2b_demand_candidates(request.user, project=project),
            "can_change": request.user.has_perm("projects.change_project")
            and project.state == ProjectState.DRAFT,
            "can_manage_forecast": request.user.has_perm("projects.change_project")
            and project.state in (ProjectState.DRAFT, ProjectState.ACTIVE, ProjectState.ON_HOLD),
            "can_link": request.user.has_perm("projects.link_project_salesorder")
            and project.state not in (ProjectState.COMPLETED, ProjectState.CANCELLED),
        },
    )


@login_required
def project_edit(request, pk):
    _require(request.user, "projects.change_project")
    project = _project(request.user, pk)
    form = ProjectForm(request.POST or None, instance=project, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            project = update_draft_project(
                project,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_values(form),
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(
        request, "projects/project_form.html", {"form": form, "title": f"Edit {project.code}"}
    )


@login_required
def budget_add(request, pk):
    _require(request.user, "projects.change_project")
    project = _project(request.user, pk)
    form = ProjectBudgetLineForm(request.POST or None, user=request.user, project=project)
    if request.method == "POST" and form.is_valid():
        try:
            add_project_budget_line(
                project, actor=request.user, reason=form.cleaned_data["reason"], **_values(form)
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(
        request,
        "projects/budget_form.html",
        {"form": form, "project": project, "title": "Add budget line"},
    )


@login_required
def sales_order_link(request, pk):
    _require(request.user, "projects.link_project_salesorder")
    project = _project(request.user, pk)
    form = ProjectSalesOrderLinkForm(request.POST or None, user=request.user, project=project)
    if request.method == "POST" and form.is_valid():
        try:
            link_sales_order(
                project,
                form.cleaned_data["sales_order"],
                actor=request.user,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(request, "projects/link_form.html", {"form": form, "project": project})


@login_required
def project_transition(request, pk, action):
    project = _project(request.user, pk)
    permissions = {
        "activate": "projects.activate_project",
        "hold": "projects.hold_project",
        "release": "projects.hold_project",
        "complete": "projects.complete_project",
        "cancel": "projects.cancel_project",
    }
    services = {
        "activate": activate_project,
        "hold": hold_project,
        "release": release_project,
        "complete": complete_project,
        "cancel": cancel_project,
    }
    if action not in permissions:
        raise PermissionDenied
    _require(request.user, permissions[action])
    form = ProjectReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            kwargs = {} if action == "activate" else {"reason": form.cleaned_data["reason"]}
            services[action](project, actor=request.user, **kwargs)
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(
        request,
        "projects/transition_form.html",
        {"form": form, "project": project, "action": action},
    )


@login_required
def forecast_add(request, pk):
    _require(request.user, "projects.change_project")
    project = _project(request.user, pk)
    form = ProjectForecastLineForm(request.POST or None, user=request.user, project=project)
    if project.state in (ProjectState.COMPLETED, ProjectState.CANCELLED):
        form.add_error(None, "Completed or cancelled Projects cannot receive forecast lines.")
    elif request.method == "POST" and form.is_valid():
        try:
            add_project_forecast_line(
                project,
                actor=request.user,
                reason=form.cleaned_data.get("reason", ""),
                **_values(form),
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(
        request,
        "projects/forecast_form.html",
        {"form": form, "project": project, "title": "Add forecast line"},
    )


@login_required
def forecast_edit(request, pk, line_pk):
    _require(request.user, "projects.change_project")
    project = _project(request.user, pk)
    line = get_object_or_404(project.forecast_lines, pk=line_pk)
    form = ProjectForecastLineForm(
        request.POST or None, instance=line, user=request.user, project=project
    )
    if project.state in (ProjectState.COMPLETED, ProjectState.CANCELLED):
        form.add_error(None, "Completed or cancelled Projects cannot be edited.")
    elif request.method == "POST" and form.is_valid():
        try:
            update_project_forecast_line(
                line,
                actor=request.user,
                reason=form.cleaned_data.get("reason", ""),
                **_values(form),
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(
        request,
        "projects/forecast_form.html",
        {"form": form, "project": project, "line": line, "title": "Edit forecast line"},
    )


@login_required
def forecast_remove(request, pk, line_pk):
    _require(request.user, "projects.change_project")
    project = _project(request.user, pk)
    line = get_object_or_404(project.forecast_lines, pk=line_pk)
    form = ProjectReasonForm(request.POST or None)
    if project.state in (ProjectState.COMPLETED, ProjectState.CANCELLED):
        form.add_error(None, "Completed or cancelled Projects cannot be edited.")
    elif request.method == "POST" and form.is_valid():
        try:
            remove_project_forecast_line(
                line,
                actor=request.user,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("projects:detail", pk=project.pk)
    return render(
        request,
        "projects/forecast_confirm_delete.html",
        {"form": form, "project": project, "line": line},
    )
