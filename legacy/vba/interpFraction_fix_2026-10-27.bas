' Correction to interpFraction_fix_2026-10-26.bas (M. Holt / Claude, 27 Oct 2026),
' confirmed by the lead author 29 Oct 2026. Only the outlet-side tests and ramp change:
' pipeSegQTY -> pipeSegQTY + 1, so that A(n) = A(N - n) over the called range 1..N-1
' (arrayA has N + 1 nodes) and B(n) = B(N - 1 - n). Inlet side identical to 26 Oct.

Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
    ' A nodes: called for n = 1 To pipeSegQTY - 1 (arrayA is 0 To pipeSegQTY)
    Const extQTY = 4  'QTY at each end are not active
    If n + 1 < extQTY + 0.5 Then
        interpFractionA = 0
    ElseIf n + 1 < pivotSegQTY Then
        interpFractionA = ((n + 0.5 - extQTY) / (pivotSegQTY - extQTY)) ^ 2
    ElseIf n + 1 > pipeSegQTY + 1 - extQTY + 0.5 Then
        interpFractionA = 0
    ElseIf n + 1 > pipeSegQTY + 2 - pivotSegQTY Then
        interpFractionA = ((pipeSegQTY + 1 - extQTY - n - 0.5) / (pivotSegQTY - extQTY)) ^ 2
    Else
        interpFractionA = 1
    End If
End Function

Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
    ' B cells: called for n = 0 To pipeSegQTY - 1
    Const extQTY = 4  'QTY at each end are not active
    If n + 1 < extQTY + 0.5 Then
        interpFractionB = 0
    ElseIf n + 1 < pivotSegQTY Then
        interpFractionB = ((n + 1 - extQTY) / (pivotSegQTY - extQTY)) ^ 2
    ElseIf n + 1 > pipeSegQTY + 1 - extQTY - 0.5 Then
        interpFractionB = 0
    ElseIf n + 1 > pipeSegQTY + 1.5 - pivotSegQTY Then
        interpFractionB = ((pipeSegQTY + 1 - extQTY - n - 1) / (pivotSegQTY - extQTY)) ^ 2
    Else
        interpFractionB = 1
    End If
End Function
