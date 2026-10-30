"""Formulas puras, sem acesso a fontes ou interpretacao por modelo."""
import math


def _area(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise ValueError("area deve ser finita e nao negativa")
    return value


def convert_area(area_ha,unit):
    _area(area_ha)
    factors={"ha":1,"km2":0.01,"m2":10000}
    if unit not in factors:raise ValueError("unidade de area invalida")
    return area_ha*factors[unit]


def temporal_change(initial_ha,final_ha):
    _area(initial_ha);_area(final_ha)
    delta=final_ha-initial_ha
    return {"delta_ha":delta,"reduction_ha":max(0, -delta),
            "change_percent":100*delta/initial_ha if initial_ha else None,
            "undefined_reason":"base_inicial_zero" if not initial_ha else None}


def share_percent(class_ha,observed_ha):
    _area(class_ha);_area(observed_ha)
    if class_ha>observed_ha and not math.isclose(class_ha,observed_ha,rel_tol=1e-12,abs_tol=1e-9):raise ValueError("area de classe excede suporte observado")
    return 100*class_ha/observed_ha if observed_ha else None


def percentage_point_change(initial_class,initial_support,final_class,final_support):
    a=share_percent(initial_class,initial_support)
    b=share_percent(final_class,final_support)
    return b-a if a is not None and b is not None else None


def convert_signed_area(value_ha,unit):
    """Diferencas podem ser negativas; a conversao preserva o sinal e nao arredonda."""
    if isinstance(value_ha,bool) or not isinstance(value_ha,(int,float)) or not math.isfinite(value_ha):
        raise ValueError("diferenca deve ser finita")
    return math.copysign(convert_area(abs(value_ha),unit),value_ha)
