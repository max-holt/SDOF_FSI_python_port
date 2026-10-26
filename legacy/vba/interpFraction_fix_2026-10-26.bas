' Lead author's corrected interpFractionA / interpFractionB, received 2026-10-26.
' Replaces lines 105-134 of "Existing Code.bas" (which is frozen and not edited).
' Ported as the "fixed" fraction_profile of surge_sdof.moc.interp_fractions (F-4,
' DEVIATIONS D-4); the original functions remain the "legacy" profile.
Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
    ' For n = 0 To pipeSegQTY - 1
    Const extQTY = 4  'QTY at each end are not active
    If n + 1 < extQTY + 0.5 Then
        interpFractionA = 0
    ElseIf n + 1 < pivotSegQTY Then
        interpFractionA = ((n + 0.5 - extQTY) / (pivotSegQTY - extQTY)) ^ 2
    ElseIf n + 1 > pipeSegQTY - extQTY + 0.5 Then
        interpFractionA = 0
    ElseIf n + 1 > pipeSegQTY + 1 - pivotSegQTY Then
        interpFractionA = ((pipeSegQTY - extQTY - n - 0.5) / (pivotSegQTY - extQTY)) ^ 2
    Else
        interpFractionA = 1
    End If
End Function

Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
    ' For n = 0 To pipeSegQTY - 1
    Const extQTY = 4  'QTY at each end are not active
    If n + 1 < extQTY + 0.5 Then
        interpFractionB = 0
    ElseIf n + 1 < pivotSegQTY Then
        interpFractionB = ((n + 1 - extQTY) / (pivotSegQTY - extQTY)) ^ 2
    ElseIf n + 1 > pipeSegQTY - extQTY - 0.5 Then
        interpFractionB = 0
    ElseIf n + 1 > pipeSegQTY + 0.5 - pivotSegQTY Then
        interpFractionB = ((pipeSegQTY - extQTY - n - 1) / (pivotSegQTY - extQTY)) ^ 2
    Else
        interpFractionB = 1
    End If
End Function
