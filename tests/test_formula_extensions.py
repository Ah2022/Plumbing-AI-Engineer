"""Independent ordinary Excel semantics; errors never mask unsupported functions."""
import math
import pytest
from tests.test_workbooks import book
from workbooks.formulas import Evaluator,FormulaError,UnsupportedFormula


@pytest.mark.parametrize('formula,expected',[
    ('AVERAGE(A1:B1)',3.5),('COUNT(A1:B1)',2),('COUNTA(A1:B1)',2),
    ('COUNT(TRUE,"3","abc")',2),('SUM(TRUE,"3")',4),('AVERAGE(TRUE,"3")',2),
    ('IFERROR(1/0,7)',7),('IFERROR(3,1/0)',3),('IFERROR(MATCH(99,A1:B1,0),0)',0),
    ('AND(A1>0,B1=4)',True),('OR(FALSE,A1>4)',False),('NOT(FALSE)',True),
    ('POWER(2,3)',8),('EXP(0)',1),('LN(EXP(2))',2),('LOG(100)',2),('LOG(8,2)',3),('LOG10(1000)',3),
    ('PI()',math.pi),('ROUNDDOWN(-2.99,0)',-2),('TAN(0)',0),('ASIN(1)',math.pi/2),('ACOS(1)',0),('ATAN(1)',math.pi/4),
    ('SUMPRODUCT(A1:B1,A1:B1)',25),('SUMIF(A1:B1,">3")',4),('COUNTIF(A1:B1,">=3")',2),
    ('SUMIFS(A1:B1,A1:B1,">3")',4),('COUNTIFS(A1:B1,">2",A1:B1,"<4")',1),
])
def test_ordinary_formulas(formula,expected):
    r=Evaluator(book(formula)).cell('Calc','C1')
    assert r==pytest.approx(expected)


def test_unsupported_formula_cannot_be_hidden_by_iferror():
    with pytest.raises(UnsupportedFormula):Evaluator(book('IFERROR(WEIGHT2SUM(A1),7)')).cell('Calc','C1')


def test_criteria_wildcards_escaping_and_blanks():
    extra={'A2':dict(value='oxygen',formula=None,error=False),'B2':dict(value='O*',formula=None,error=False)}
    assert Evaluator(book('COUNTIF(A2:B2,"o*")',extra)).cell('Calc','C1')==2
    assert Evaluator(book('COUNTIF(A2:B2,"o~*")',extra)).cell('Calc','C1')==1
    assert Evaluator(book('COUNTA(A2:B2)',extra)).cell('Calc','C1')==2


def test_criteria_ranges_do_not_silently_resize_and_unsupported_text_ordering_stays_explicit():
    with pytest.raises(UnsupportedFormula):Evaluator(book('SUMIF(A1:B1,">0",A1)')).cell('Calc','C1')
    with pytest.raises(UnsupportedFormula):Evaluator(book('COUNTIF(A1:B1,">abc")')).cell('Calc','C1')
