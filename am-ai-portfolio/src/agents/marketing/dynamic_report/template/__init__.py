from .employee_North_visit import EmployeeNorthVisitTemplate
from .employee_visit import EmployeeVisitTemplate
from .end import EndTemplate
from .team_visit import TeamVisitTemplate
from .company_visit import CompanyVisitTemplate
from .requirement import CompanyRequirementTemplate

TEMPLATE_REGISTRY = {
    "employee_visit": EmployeeVisitTemplate(),
    "team_visit": TeamVisitTemplate(),
    "company_visit": CompanyVisitTemplate(),
    "company_requirement": CompanyRequirementTemplate(),
    "employee_north_visit": EmployeeNorthVisitTemplate(),
    "end":EndTemplate()
}
