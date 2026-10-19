Option Explicit

Function min(valueA As Variant, valueB As Variant) As Variant
    If valueA < valueB Then
        min = valueA
    Else
        min = valueB
    End If
End Function

Function max(valueA As Variant, valueB As Variant) As Variant
    If valueA > valueB Then
        max = valueA
    Else
        max = valueB
    End If
End Function

Function minUnsigned(valueA As Variant, valueB As Variant) As Variant
    If Abs(valueA) < Abs(valueB) Then
        If valueB = 0 Then
            minUnsigned = valueA
        Else
            minUnsigned = valueA * sign(CDbl(valueB))
        End If
    Else
        If valueA = 0 Then
            minUnsigned = valueB
        Else
            minUnsigned = valueB * sign(CDbl(valueA))
        End If
    End If
End Function

Function maxUnsigned(valueA As Variant, valueB As Variant) As Variant
    If Abs(valueA) > Abs(valueB) Then
        If valueB = 0 Then
            maxUnsigned = valueA
        Else
            maxUnsigned = valueA * sign(CDbl(valueB))
        End If
    Else
        If valueA = 0 Then
            maxUnsigned = valueB
        Else
            maxUnsigned = valueB * sign(CDbl(valueA))
        End If
    End If
End Function

Function sign(val As Double, Optional lim As Double = 0) As Double
    If val > lim Then
        sign = 1
    ElseIf val < -lim Then
        sign = -1
    Else
        sign = 0
    End If
End Function

Function getDimension(var As Variant) As Long
    On Error GoTo Err
    Dim i As Long
    Dim tmp As Long
    i = 0
    Do While True
        i = i + 1
        tmp = UBound(var, i)
    Loop
Err:
    getDimension = i - 1
End Function

Function AddDimension(arr As Variant, newLBound As Long, newUBound As Long) As Double()
    Dim i As Long
    Dim arrOut() As Double
    ReDim arrOut(1 To UBound(arr) + LBound(arr) + 1, newLBound To newUBound)
    For i = LBound(arr) To UBound(arr)
        arrOut(i - LBound(arr) + 1, newLBound) = arr(i)
    Next
    AddDimension = arrOut
End Function

Function ArrayStartOne(arr As Variant) As Double()
    Dim i As Long
    Dim j As Long
    Dim arrOut() As Double
    ReDim arrOut(1 To UBound(arr, 1) + LBound(arr, 1) + 1, 1 To UBound(arr, 2) + LBound(arr, 2) + 1)
    For i = LBound(arr, 1) To UBound(arr, 1)
        For j = LBound(arr, 2) To UBound(arr, 2)
            arrOut(i - LBound(arr, 1) + 1, j - LBound(arr, 2) + 1) = arr(i, j)
        Next
    Next
    AddDimension = arrOut
End Function

Function floor(val As Variant) As Long
    floor = max(CLng(val - 0.5), CLng(val + 0.5) - 1)
End Function

Function modDbl(num As Variant, div As Variant) As Double
    modDbl = num - (floor(CDbl(num) / CDbl(div)) * div)
End Function

Function interpFractionA(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
    ' For n = 0 To pipeSegQTY - 1
    Const extQTY = 4  'QTY at each end are not active
    If n < extQTY Then
        interpFractionA = 0
    ElseIf n < pivotSegQTY Then
        interpFractionA = ((n - 0.5 - extQTY) / (pivotSegQTY - extQTY)) ^ 2
    ElseIf n > pipeSegQTY - extQTY Then
        interpFractionA = 0
    ElseIf n > pipeSegQTY - pivotSegQTY Then
        interpFractionA = ((pipeSegQTY - 0.5 - extQTY - n) / (pivotSegQTY - extQTY)) ^ 2
    Else
        interpFractionA = 1
    End If
End Function

Function interpFractionB(n As Long, pivotSegQTY As Long, pipeSegQTY As Long) As Double
    ' For n = 0 To pipeSegQTY - 1
    Const extQTY = 4  'QTY at each end are not active
    If n < 3 Then
        interpFractionB = 0
    ElseIf n < pivotSegQTY Then
        interpFractionB = ((n - extQTY) / (pivotSegQTY - extQTY)) ^ 2
    ElseIf n > pipeSegQTY - extQTY Then
        interpFractionB = 0
    ElseIf n > pipeSegQTY - pivotSegQTY Then
        interpFractionB = ((pipeSegQTY - 1 - extQTY - n) / (pivotSegQTY - extQTY)) ^ 2
    Else
        interpFractionB = 1
    End If
End Function

Function solvePoly(varA As Double, varB As Double, varC As Double) As Double
    Const relax = 0.25
    Dim lenVal As Double
    Dim grad As Double
    Dim errorVal As Double
    Dim i As Integer
    lenVal = (-varA / varB) ^ (1 / 3)
    For i = 1 To 100
        errorVal = varA + varB * (lenVal ^ 3) + varC * (lenVal ^ 4)
        If Abs(errorVal / varA) < 0.000001 Then
            Exit For
        End If
        grad = 3 * varB * (lenVal ^ 2) + 4 * varC * (lenVal ^ 3)
        lenVal = lenVal - relax * errorVal / grad
    Next
    solvePoly = lenVal
End Function

Function GetPressureResponse(valvePattern As Variant, closureTime As Double, celerity As Double, density As Double, timeStep As Double, pressureDropFromPump As Double, flowRate As Double, pipeArea As Double, valveCv As Double, lengthToPump As Double, pumpRampPressure As Double) As Double()
    'returns the pressure response at valve
    'closureTime = valve closure time (sec)
    'celerity = fluid/pipe effective pressure wave speed (m/sec)
    'density = fluid density (kg/m3)
    'timeStep = simulation time step (sec)
    'pressureDropFromPump = total pressure drop from pump to valve (bar) @ flowRate
    'flowRate = simulation initial flowrate (m3/h)
    'pipeArea = pipe flowing cress-sectional area (mm^2)
    'valveCv = (flowRate in US gallons per minute)*(SG/pressure drop over valve in psi)^0.5
    'lengthToPump = length of pipe to the pump (m)
    'pumpRampPressure = difference in pressure between operating and shut-in (bar)
    
    Dim i As Long
    Dim j As Long
    Dim imax As Long
    Dim jmax As Long
    Dim k As Long
    Dim totInd As Long
    Dim outMax As Long
    Dim pipeSegQTY As Long
    
    Dim closure As Double
    Dim factor As Double
    Dim frac As Double
    Dim rhoC As Double
    Dim v As Double
    Dim loss As Double
    Dim velAtPump As Double
    Dim sysMat(0 To 1) As Double
    
    Dim valveLoss As Double
    Dim pipeLoss As Double
    Dim velocityInitial As Double
    Dim velInitLocal As Double
    Dim valveDPInitial As Double
    
    Dim resultArray() As Double
    Dim arrayA() As Double
    Dim arrayB() As Double
    
    If TypeName(valvePattern) = "Range" Then
        valvePattern = valvePattern.Value
    Else
        If getDimension(valvePattern) < 2 Then
            valvePattern = AddDimension(valvePattern, 1, 1)
        ElseIf LBound(valvePattern, 1) <> 1 Or LBound(valvePattern, 2) <> 1 Then
            valvePattern = ArrayStartOne(valvePattern)
        End If
    End If
    
    outMax = CLng(closureTime / timeStep)
    pipeSegQTY = 1 + CLng(min(outMax, lengthToPump / (celerity * timeStep)) / 2)
    
    ReDim resultArray(0 To outMax) As Double
    ReDim arrayA(0 To 1, 0 To pipeSegQTY) As Double
    ReDim arrayB(0 To 1, 0 To pipeSegQTY) As Double
    
    factor = UBound(valvePattern, 1) * UBound(valvePattern, 2) * timeStep / closureTime
    
    rhoC = density * celerity
    
    velocityInitial = -flowRate * 1000000 / (pipeArea * 60 * 60) 'm/s
    valveLoss = (density / 1000) * 100000 / ((((valveCv * 0.865 * 1000000) / (pipeArea * 60 * 60))) ^ 2) 'Pa/(m/s)^2
    valveDPInitial = valveLoss * (velocityInitial ^ 2) 'Pa
    pipeLoss = pressureDropFromPump * 100000 / ((1 + pipeSegQTY * 2)) 'Pa/segment
    
    For i = 0 To pipeSegQTY
        arrayA(0, i) = i * 2 * pipeLoss + valveDPInitial
        arrayB(0, i) = (1 + i * 2) * pipeLoss + valveDPInitial
        arrayA(1, i) = -i * 2 * pipeLoss / rhoC + velocityInitial
        arrayB(1, i) = -(1 + i * 2) * pipeLoss / rhoC + velocityInitial
    Next
    
    velAtPump = arrayB(1, pipeSegQTY)
    
    'pipeLoss = pipeLoss / (velocityInitial ^ 2) 'Pa/(m/s)^2
    
    'self.mocMat = self.invertMatrix([[-1.0,-1.0/self.rhoC],
    '                                 [-1.0,+1.0/self.rhoC]])
    
    'self.mocMat = [[-0.5,-0.5],
    '               [-self.rhoC/2,+self.rhoC/2]]
    
    '        mat = [[loss-vL-pL/self.rhoC],
    '               [loss-vR+pR/self.rhoC]]
    
    For totInd = 0 To outMax
        ' every loop is 2 time steps
        i = modDbl(floor(totInd * factor * 2), UBound(valvePattern, 1)) + 1
        j = floor(totInd * factor * 2 / UBound(valvePattern, 1)) + 1
        If i >= UBound(valvePattern, 1) And j < UBound(valvePattern, 2) Then
            i = UBound(valvePattern, 1)
            jmax = min(j + 1, UBound(valvePattern, 2))
            imax = 1
        Else
            If i > UBound(valvePattern, 1) Then
                i = UBound(valvePattern, 1)
            End If
            jmax = j
            imax = min(i + 1, UBound(valvePattern, 1))
        End If
        ' get valve position
        If j > UBound(valvePattern, 2) Then
            closure = valvePattern(UBound(valvePattern, 1), UBound(valvePattern, 2))
        ElseIf i = imax And j = jmax Then
            closure = valvePattern(i, j)
        Else
            frac = ((i - 1) + (j - 1) * UBound(valvePattern, 1) - totInd * factor * 2) / ((i - 1) + (j - 1) * UBound(valvePattern, 1) - ((imax - 1) + (jmax - 1) * UBound(valvePattern, 1)))
            closure = valvePattern(i, j) * (1 - frac) + valvePattern(imax, jmax) * frac
        End If
        ' valve pressure is determined by the velocity
        If closure < 0.999999999 Then
            arrayA(1, 0) = (arrayA(1, 0) + arrayB(1, 0)) / 2 + (arrayA(0, 0) - arrayB(0, 0)) / (2 * rhoC)
            arrayA(0, 0) = min(((valveLoss / (1 - closure)) * (arrayA(1, 0) ^ 2)), max(arrayB(0, 0), (arrayA(0, 0) + arrayB(0, 0)) / 2 - arrayA(1, 0) * rhoC))
        Else
            arrayA(1, 0) = 0
            arrayA(0, 0) = max(arrayB(0, 0), arrayB(0, 0) - arrayB(1, 0) * rhoC)
        End If
        ' MoC
        For i = 1 To min(pipeSegQTY, totInd)
            v = (arrayB(1, i - 1) + arrayB(1, i)) / 2
            velInitLocal = i * 2 * pipeLoss / rhoC + velocityInitial
            loss = v * min(0.9, Abs(v) * pipeLoss / (rhoC * (velInitLocal ^ 2)))
    
            sysMat(0) = -loss - arrayB(1, i - 1) - arrayB(0, i - 1) / rhoC
            sysMat(1) = loss - arrayB(1, i) + arrayB(0, i) / rhoC
            
            arrayA(1, i) = -(sysMat(0) + sysMat(1)) / 2
            arrayA(0, i) = max(0, -(sysMat(0) - sysMat(1)) * rhoC / 2)
        Next
        ' pump pressure is determined by the velocity
        arrayB(0, pipeSegQTY) = max(0, valveDPInitial + 100000 * (pressureDropFromPump + pumpRampPressure * (1 - (min(0, arrayA(1, pipeSegQTY)) / velAtPump) ^ 2)))
        arrayB(1, pipeSegQTY) = min(0, arrayA(1, pipeSegQTY))
        ' MoC
        For i = 0 To min(pipeSegQTY - 1, totInd)
            v = (arrayA(1, i) + arrayA(1, i + 1)) / 2
            velInitLocal = (1 + i * 2) * pipeLoss / rhoC + velocityInitial
            loss = v * min(0.9 * rhoC, Abs(v) * pipeLoss / (rhoC * (velInitLocal ^ 2)))
    
            sysMat(0) = -loss - arrayA(1, i) - arrayA(0, i) / rhoC
            sysMat(1) = loss - arrayA(1, i + 1) + arrayA(0, i + 1) / rhoC
            
            arrayB(1, i) = -(sysMat(0) + sysMat(1)) / 2
            arrayB(0, i) = max(0, -(sysMat(0) - sysMat(1)) * rhoC / 2)
        Next
    
        resultArray(totInd) = arrayA(0, 0)
    
    Next
    
    GetPressureResponse = resultArray
End Function

Function GetPeakResponse(forceHistory As Variant, stepQTY As Integer, sampleFreq As Double, physicalLength As Double, flexuralRigidityEI As Double, celerity As Double, massPerUnitLen As Double, dampingPercent As Double, dynamicFric As Double, natFreq As Double, Optional restrainFreqRatio As Double = 1, Optional gap As Double = 0, Optional outputType As Integer = 0) As Double()
    'returns the peak displacement response (consistent unites except dynamicFric)
    'forceHistory = force-time history at one location
    'stepQTY = simulation frequency (steps per sample)
    'sampleFreq = frequency of time values for data in forceHistory
    'physicalLength = length between elbows
    'flexuralRigidityEI = E * I
    'celerity = effective progression speed of force History
    'massPerUnitLen = mass / physicalLength
    'dampingPercent = percent critical damping
    'dynamicFric = friction acting on mass to resist movement (assumes units are m,sec)
    'natFreq = sqrt(k/m)
    'restrainFreqRatio = ratio of natural frequency when support gaps are closed to when support gaps are open
    'gap = support gaps (measured effective gap at center of mass or equivalently mode maximum displacement)
    
    Const pi = 3.14159265358979
    
    Dim i As Long
    Dim j As Long
    Dim imax As Long
    Dim jmax As Long
    Dim k As Long
    Dim totInd As Long
    
    Dim forceA As Double
    Dim forceB As Double
    Dim x As Double
    Dim v As Double
    Dim a As Double
    Dim vNew As Double
    Dim aNew As Double
    Dim xMax As Double
    Dim vMax As Double
    Dim aMax As Double
    Dim FMax As Double
    Dim xZero As Double
    
    Dim unballanceStepQTY As Double
    Dim mass As Double
    Dim stiffness As Double
    Dim fricAcc As Double
    Dim portalFrameHeight As Double
    
    Dim damping As Double
    Dim dt As Double
    
    Dim iB As Long
    Dim jB As Long
    Dim iBmax As Long
    Dim jBmax As Long
    
    Dim kOverlap As Long
    Dim outMax As Long
    
    Dim resultArray() As Double
    
    If TypeName(forceHistory) = "Range" Then
        forceHistory = forceHistory.Value
    Else
        If getDimension(forceHistory) < 2 Then
            forceHistory = AddDimension(forceHistory, 1, 1)
        ElseIf LBound(forceHistory, 1) <> 1 Or LBound(forceHistory, 2) <> 1 Then
            forceHistory = ArrayStartOne(forceHistory)
        End If
    End If
    
    unballanceStepQTY = physicalLength / (celerity / sampleFreq)
    
    outMax = UBound(forceHistory, 1) * UBound(forceHistory, 2) + CLng(unballanceStepQTY)
    ReDim resultArray(1 To outMax * 2) As Double
    
    kOverlap = CLng((unballanceStepQTY - floor(unballanceStepQTY)) * stepQTY)
    
    dt = 1 / (sampleFreq * stepQTY)
    
    portalFrameHeight = solvePoly(-12 * flexuralRigidityEI / ((2 * pi * natFreq) ^ 2), physicalLength * massPerUnitLen, massPerUnitLen * 4 / 3)
    For i = 0 To 10
        portalFrameHeight = solvePoly(-12 * flexuralRigidityEI * (0.5 + 1.5 * ((portalFrameHeight / (physicalLength + portalFrameHeight)) ^ 2)) / ((2 * pi * natFreq) ^ 2), physicalLength * massPerUnitLen, massPerUnitLen * 4 / 3)
    Next
    
    mass = (physicalLength + portalFrameHeight * 4 / 3) * massPerUnitLen
    stiffness = ((natFreq * 2 * pi) ^ 2) * mass
    damping = 2 * ((stiffness * mass) ^ 0.5) * dampingPercent / 100
    fricAcc = 0.5 * dynamicFric * 9.81 * dt
    
    x = 0
    xMax = 0
    v = 0
    vMax = 0
    a = 0
    aMax = 0
    
    forceA = forceHistory(1, 1)
    
    totInd = 0
    For jB = 1 To 1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))
        For iB = 1 To UBound(forceHistory, 1)
            totInd = totInd + 1
            If jB > UBound(forceHistory, 2) Then
                j = UBound(forceHistory, 2)
                i = UBound(forceHistory, 1)
            Else
                j = jB
                i = iB
            End If
            If i + 1 > UBound(forceHistory, 1) And j < UBound(forceHistory, 2) Then
                jmax = min(j + 1, UBound(forceHistory, 2))
                imax = 1
            Else
                jmax = min(j, UBound(forceHistory, 2))
                imax = min(i + 1, UBound(forceHistory, 1))
            End If
            For k = 0 To stepQTY - 1
                forceB = forceHistory(i, j) * (1 - k / (stepQTY - 1)) + forceHistory(imax, jmax) * (k / (stepQTY - 1))
                
                aNew = ((forceA - forceB) - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
                If Abs(v) < fricAcc Then
                    vNew = (a + aNew) * dt / 2
                Else
                    vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
                End If
                x = x + (v + vNew) * dt / 2
                v = vNew
                a = aNew
                
                If Abs(a) > aMax Then
                    aMax = Abs(a)
                End If
                If Abs(v) > vMax Then
                    vMax = Abs(v)
                End If
                If Abs(x) > xMax Then
                    xMax = Abs(x)
                End If
                If Abs(forceA - forceB) > FMax Then
                    FMax = Abs(forceA - forceB)
                End If
                If (totInd - 1) * stepQTY + 1 + k > unballanceStepQTY * stepQTY Then
                    Exit For
                End If
            Next
            If outputType > 0 Then
                If outputType = 1 Then
                    resultArray(totInd) = x
                ElseIf outputType = 2 Then
                    resultArray(totInd) = v
                ElseIf outputType = 3 Then
                    resultArray(totInd) = a
                End If
            End If
            If totInd > unballanceStepQTY Then
                Exit For
            End If
        Next
        If totInd > unballanceStepQTY Then
            Exit For
        End If
    Next
    
    If jB > UBound(forceHistory, 2) Then
        jB = UBound(forceHistory, 2)
        iB = UBound(forceHistory, 1)
    End If
    
    For j = 1 To UBound(forceHistory, 2)
        For i = 1 To UBound(forceHistory, 1)
            totInd = totInd + 1
            If i + 1 > UBound(forceHistory, 1) And j < UBound(forceHistory, 2) Then
                jmax = min(j + 1, UBound(forceHistory, 2))
                imax = 1
            Else
                jmax = j
                imax = min(i + 1, UBound(forceHistory, 1))
            End If
            If iB + 1 > UBound(forceHistory, 1) And jB < UBound(forceHistory, 2) Then
                jBmax = min(jB + 1, UBound(forceHistory, 2))
                iBmax = 1
            Else
                jBmax = jB
                iBmax = min(iB + 1, UBound(forceHistory, 1))
            End If
            For k = 0 To stepQTY - kOverlap - 1
                forceA = forceHistory(i, j) * (1 - k / (stepQTY - 1)) + forceHistory(imax, jmax) * (k / (stepQTY - 1))
                forceB = forceHistory(iB, jB) * (1 - (k + kOverlap) / (stepQTY - 1)) + forceHistory(iBmax, jBmax) * ((k + kOverlap) / (stepQTY - 1))
            
                aNew = ((forceA - forceB) - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
                If Abs(v) < fricAcc Then
                    vNew = (a + aNew) * dt / 2
                Else
                    vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
                End If
                x = x + (v + vNew) * dt / 2
                v = vNew
                a = aNew
                
                If Abs(a) > aMax Then
                    aMax = Abs(a)
                End If
                If Abs(v) > vMax Then
                    vMax = Abs(v)
                End If
                If Abs(x) > xMax Then
                    xMax = Abs(x)
                End If
                If Abs(forceA - forceB) > FMax Then
                    FMax = Abs(forceA - forceB)
                End If
            Next
            If iB + 1 > UBound(forceHistory, 1) And jB < UBound(forceHistory, 2) Then
                jB = min(jB + 1, UBound(forceHistory, 2))
                iB = 1
            Else
                iB = min(iB + 1, UBound(forceHistory, 1))
            End If
            If iB + 1 > UBound(forceHistory, 1) And jB < UBound(forceHistory, 2) Then
                jBmax = min(jB + 1, UBound(forceHistory, 2))
                iBmax = 1
            Else
                jBmax = jB
                iBmax = min(iB + 1, UBound(forceHistory, 1))
            End If
            For k = stepQTY - kOverlap To stepQTY - 1
                forceA = forceHistory(i, j) * (1 - k / (stepQTY - 1)) + forceHistory(imax, jmax) * (k / (stepQTY - 1))
                forceB = forceHistory(iB, jB) * (1 - (k - stepQTY + kOverlap) / (stepQTY - 1)) + forceHistory(iBmax, jBmax) * ((k - stepQTY + kOverlap) / (stepQTY - 1))
            
                aNew = ((forceA - forceB) - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
                If Abs(v) < fricAcc Then
                    vNew = (a + aNew) * dt / 2
                Else
                    vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
                End If
                x = x + (v + vNew) * dt / 2
                v = vNew
                a = aNew
                
                If Abs(a) > aMax Then
                    aMax = Abs(a)
                End If
                If Abs(v) > vMax Then
                    vMax = Abs(v)
                End If
                If Abs(x) > xMax Then
                    xMax = Abs(x)
                End If
                If Abs(forceA - forceB) > FMax Then
                    FMax = Abs(forceA - forceB)
                End If
            Next
            If outputType > 0 Then
                If outputType = 1 Then
                    resultArray(totInd) = x
                ElseIf outputType = 2 Then
                    resultArray(totInd) = v
                ElseIf outputType = 3 Then
                    resultArray(totInd) = a
                End If
            End If
        Next
    Next
    xZero = x
    Do While x * xZero > 0.01
        totInd = totInd + 1
        For k = 1 To stepQTY
            
            aNew = (-(minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
            If Abs(v) < fricAcc Then
                vNew = (a + aNew) * dt / 2
            Else
                vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
            End If
            x = x + (v + vNew) * dt / 2
            v = vNew
            a = aNew
            
            If Abs(a) > aMax Then
                aMax = Abs(a)
            End If
            If Abs(v) > vMax Then
                vMax = Abs(v)
            End If
            If Abs(x) > xMax Then
                xMax = Abs(x)
            End If
            
            If x * xZero <= 0.01 Then
                xZero = 0
            End If
        Next
        If outputType > 0 Then
            If totInd <= outMax * 2 Then
                If outputType = 1 Then
                    resultArray(totInd) = x
                ElseIf outputType = 2 Then
                    resultArray(totInd) = v
                ElseIf outputType = 3 Then
                    resultArray(totInd) = a
                End If
            End If
        End If
    Loop
    
    If outputType = 0 Then
        ReDim resultArray(0 To 4) As Double
        resultArray(0) = Abs(minUnsigned(gap, xMax) + max(0, Abs(xMax) - gap) * sign(xMax) * (restrainFreqRatio ^ 2)) * stiffness ' max static equivalent
        resultArray(1) = xMax ' max displacement
        resultArray(2) = vMax ' max velocity
        resultArray(3) = aMax ' max acceloration
        resultArray(4) = FMax ' max applied force
    End If
    
    GetPeakResponse = resultArray
End Function

Function GetPeakResponseJC(forceHistory As Variant, stepQTY As Integer, sampleFreq As Double, physicalLength As Double, flexuralRigidityEI As Double, celerity As Double, massPerUnitLen As Double, fluidDensty As Double, fluidArea As Double, dampingPercent As Double, dynamicFric As Double, natFreq As Double, Optional restrainFreqRatio As Double = 1, Optional gap As Double = 0, Optional outputType As Integer = 0) As Double()
    'returns the peak displacement response (consistent unites except dynamicFric)
    'forceHistory = force-time history at one location
    'stepQTY = simulation frequency (steps per sample)
    'sampleFreq = frequency of time values for data in forceHistory
    'physicalLength = length between elbows
    'flexuralRigidityEI = E * I
    'celerity = effective progression speed of force History
    'massPerUnitLen = mass (pipe and fluid) / physicalLength
    'fluidDensty = fluid density
    'fluidArea = fluid pressure area (internal cross-sectional area of pipe)
    'dampingPercent = percent critical damping
    'dynamicFric = friction acting on mass to resist movement (assumes units are m,sec)
    'natFreq = sqrt(k/m) [assumed modeled with fluid mass included]
    'restrainFreqRatio = ratio of natural frequency when support gaps are closed to when support gaps are open
    'gap = support gaps (measured effective gap at center of mass or equivalently mode maximum displacement)
    
    Const pi = 3.14159265358979
    Const useUndamped = False
    Const dampingA = 0.25
    Const extQTY = 4  'QTY at each end are not active
    
    Dim i As Long
    Dim j As Long
    Dim imax As Long
    Dim jmax As Long
    Dim k As Long
    Dim totInd As Long
    
    Dim m As Long
    Dim n As Long
    Dim p As Long
    
    Dim forceA As Double
    Dim forceB As Double
    Dim x As Double
    Dim v As Double
    Dim a As Double
    Dim vNew As Double
    Dim aNew As Double
    Dim xMax As Double
    Dim vMax As Double
    Dim aMax As Double
    Dim FMax As Double
    Dim xZero As Double
    Dim vAv As Double
    
    Dim pipeSegQTY As Long
    Dim pivotSegQTY As Long
    Dim portalFrameHeight As Double
    Dim dacayFactor As Double
    
    Dim arrayA() As Double
    Dim arrayB() As Double
    
    Dim contA0(0 To 1, -3 To 0, 1 To 2) As Double
    Dim contAN(0 To 1, -3 To 0, -2 To -1) As Double
    
    Dim rhoC As Double
    Dim dv As Double
    Dim dF As Double
    
    Dim unballanceStepQTY As Double
    Dim mass As Double
    Dim stiffness As Double
    Dim fricAcc As Double
    
    Dim damping As Double
    Dim dt As Double
    
    Dim iB As Long
    Dim jB As Long
    Dim iBmax As Long
    Dim jBmax As Long
    
    Dim kOverlap As Long
    Dim outMax As Long
    
    Dim resultArray() As Double
    
    If TypeName(forceHistory) = "Range" Then
        forceHistory = forceHistory.Value
    Else
        If getDimension(forceHistory) < 2 Then
            forceHistory = AddDimension(forceHistory, 1, 1)
        ElseIf LBound(forceHistory, 1) <> 1 Or LBound(forceHistory, 2) <> 1 Then
            forceHistory = ArrayStartOne(forceHistory)
        End If
    End If
    
    unballanceStepQTY = physicalLength / (celerity / sampleFreq)
    
    outMax = UBound(forceHistory, 1) * UBound(forceHistory, 2) + CLng(unballanceStepQTY)
    ReDim resultArray(1 To outMax * 2) As Double
    
    kOverlap = CLng((unballanceStepQTY - floor(unballanceStepQTY)) * stepQTY)
    
    dt = 1 / (sampleFreq * stepQTY)
    
    portalFrameHeight = solvePoly(-12 * flexuralRigidityEI / ((2 * pi * natFreq) ^ 2), physicalLength * massPerUnitLen, massPerUnitLen * 4 / 3)
    For i = 0 To 10
        portalFrameHeight = solvePoly(-12 * flexuralRigidityEI * (0.5 + 1.5 * ((portalFrameHeight / (physicalLength + portalFrameHeight)) ^ 2)) / ((2 * pi * natFreq) ^ 2), physicalLength * massPerUnitLen, massPerUnitLen * 4 / 3)
    Next
    
    mass = (portalFrameHeight * 4 / 3) * massPerUnitLen + physicalLength * (massPerUnitLen - fluidDensty * fluidArea) ' remove core fluid to get rigid mass
    stiffness = ((natFreq * 2 * pi) ^ 2) * (physicalLength + portalFrameHeight * 4 / 3) * massPerUnitLen ' assume total mass has same bases as natural frequency (fluid is included in CAESAR)
    damping = 2 * ((stiffness * ((physicalLength + portalFrameHeight * 4 / 3) * massPerUnitLen)) ^ 0.5) * dampingPercent / 100 ' assume critical damping is relative to total mass
    fricAcc = 0.5 * dynamicFric * 9.81 * dt * ((physicalLength + portalFrameHeight * 4 / 3) * massPerUnitLen) / mass ' mass correction from frictional to inertial
    
    dacayFactor = 2 ^ ((celerity * dt) / physicalLength)
    
    pivotSegQTY = extQTY + CLng(portalFrameHeight / (2 * celerity * dt))
    pipeSegQTY = 2 + CLng(physicalLength / (4 * celerity * dt) + pivotSegQTY) * 2
    
    If pipeSegQTY - 2 * pivotSegQTY <= 2 Then
        ' insufficient length, use lumped mass
        GetPeakResponseJC = GetPeakResponse(forceHistory, stepQTY, sampleFreq, physicalLength, flexuralRigidityEI, celerity, massPerUnitLen, dampingPercent, dynamicFric, natFreq, restrainFreqRatio, gap, outputType)
        Exit Function
    End If
    
    ReDim arrayA(0 To 1, 0 To pipeSegQTY) As Double
    ReDim arrayB(0 To 1, 0 To pipeSegQTY - 1) As Double
    
    For m = 0 To 1 ' loop over states
        For p = -3 To 0 ' loop over past
            For n = 1 To 2 ' loop over neighbours
                contA0(m, p, n) = 0
            Next
            For n = -2 To -1
                contAN(m, p, n) = 0
            Next
        Next
        For n = 0 To pipeSegQTY - 1
            arrayA(m, n) = 0
            arrayB(m, n) = 0
        Next
        arrayA(m, pipeSegQTY) = 0
    Next
    
    rhoC = fluidDensty * celerity
    
    x = 0
    xMax = 0
    v = 0
    vMax = 0
    a = 0
    aMax = 0
    dF = 0
    
    forceA = forceHistory(1, 1)
    
    On Error GoTo ErrFound
    
    totInd = 0
    For jB = 1 To 1 + CLng(unballanceStepQTY / UBound(forceHistory, 2))
        For iB = 1 To UBound(forceHistory, 1)
            totInd = totInd + 1
            If jB > UBound(forceHistory, 2) Then
                j = UBound(forceHistory, 2)
                i = UBound(forceHistory, 1)
            Else
                j = jB
                i = iB
            End If
            If i + 1 > UBound(forceHistory, 1) And j < UBound(forceHistory, 2) Then
                jmax = min(j + 1, UBound(forceHistory, 2))
                imax = 1
            Else
                jmax = min(j, UBound(forceHistory, 2))
                imax = min(i + 1, UBound(forceHistory, 1))
            End If
            For k = 0 To stepQTY - 1
                ' MoC
                If modDbl(k + (totInd - 1) * stepQTY, 2) = 0 Then
                    ' update even cells
                    vAv = arrayA(1, pipeSegQTY)
                    For n = 0 To pipeSegQTY - 1
                        vAv = vAv + arrayA(1, n)
                        vAv = vAv + arrayB(1, n)
                    Next
                    vAv = vAv / (2 * pipeSegQTY - 1)
                    If useUndamped Then
                        For m = 0 To 1
                            ' https://docs.aft.com/impulse/InfinitePipeTransientTheory.html
                            arrayA(m, 0) = 3 * arrayB(m, 0) - 3 * contA0(m, -2, 1) + contA0(m, -3, 2) - m * vAv
                            arrayA(m, pipeSegQTY) = 3 * arrayB(m, pipeSegQTY - 1) - 3 * contAN(m, -2, -1) + contAN(m, -3, -2) - m * vAv
                            
                            contA0(m, -2, 1) = contA0(m, 0, 1) - m * vAv
                            contA0(m, 0, 1) = arrayB(m, 0) - m * vAv
                            contA0(m, -3, 2) = contA0(m, -1, 2) - m * vAv
                            contA0(m, -1, 2) = arrayA(m, 1) - m * vAv
                            
                            contAN(m, -2, -1) = contAN(m, 0, -1) - m * vAv
                            contAN(m, 0, -1) = arrayB(m, pipeSegQTY - 1) - m * vAv
                            contAN(m, -3, -2) = contAN(m, -1, -2) - m * vAv
                            contAN(m, -1, -2) = arrayA(m, pipeSegQTY - 2) - m * vAv
                        Next
                    Else
                        arrayA(0, 0) = arrayB(0, 0) / dacayFactor
                        arrayA(0, pipeSegQTY) = arrayB(0, pipeSegQTY - 1) / dacayFactor
                        arrayA(1, 0) = arrayB(1, 0) - vAv
                        arrayA(1, pipeSegQTY) = arrayB(1, pipeSegQTY - 1) - vAv
                    End If
                    For n = 1 To pipeSegQTY - 1
                        dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                        arrayA(0, n) = (arrayB(0, n - 1) + arrayB(0, n)) / 2 + rhoC * (arrayB(1, n - 1) - arrayB(1, n)) / 2
                        arrayA(1, n) = dv - vAv + (arrayB(0, n - 1) - arrayB(0, n)) / (2 * rhoC) + (arrayB(1, n - 1) + arrayB(1, n)) / 2
                    Next
                    For n = 0 To pipeSegQTY - 1
                        dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                        arrayB(1, n) = dv - vAv + arrayB(1, n)
                    Next
                    dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayA(0, pivotSegQTY) + arrayA(0, pivotSegQTY - 1) - arrayA(0, pipeSegQTY - pivotSegQTY) - arrayA(0, pipeSegQTY - pivotSegQTY + 1)) / 2
                Else
                    ' update odd cells
                    For n = 0 To pipeSegQTY - 1
                        dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                        arrayB(0, n) = (arrayA(0, n) + arrayA(0, n + 1)) / 2 + rhoC * (arrayA(1, n) - arrayA(1, n + 1)) / 2
                        arrayB(1, n) = dv + (arrayA(0, n) - arrayA(0, n + 1)) / (2 * rhoC) + (arrayA(1, n) + arrayA(1, n + 1)) / 2
                    Next
                    For n = 1 To pipeSegQTY - 1
                        dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                        arrayA(1, n) = dv + arrayA(1, n)
                    Next
                    dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayB(0, pivotSegQTY) - arrayB(0, pipeSegQTY - pivotSegQTY))
                End If
                
                ' Kinematics
                forceB = forceHistory(i, j) * (1 - k / (stepQTY - 1)) + forceHistory(imax, jmax) * (k / (stepQTY - 1))
                
                aNew = (dF + (forceA - forceB) - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
                If Abs(v) < fricAcc Then
                    vNew = (a + aNew) * dt / 2
                Else
                    vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
                End If
                x = x + (v + vNew) * dt / 2
                v = vNew
                a = aNew
                
                If Abs(a) > aMax Then
                    aMax = Abs(a)
                End If
                If Abs(v) > vMax Then
                    vMax = Abs(v)
                End If
                If Abs(x) > xMax Then
                    xMax = Abs(x)
                End If
                If Abs(forceA - forceB) > FMax Then
                    FMax = Abs(forceA - forceB)
                End If
                If (totInd - 1) * stepQTY + 1 + k > unballanceStepQTY * stepQTY Then
                    Exit For
                End If
            Next
            If outputType > 0 Then
                If outputType = 1 Then
                    resultArray(totInd) = x
                ElseIf outputType = 2 Then
                    resultArray(totInd) = v
                ElseIf outputType = 3 Then
                    resultArray(totInd) = a
                End If
            End If
            If totInd > unballanceStepQTY Then
                Exit For
            End If
        Next
        If totInd > unballanceStepQTY Then
            Exit For
        End If
    Next
    
    If jB > UBound(forceHistory, 2) Then
        jB = UBound(forceHistory, 2)
        iB = UBound(forceHistory, 1)
    End If
    
    For j = 1 To UBound(forceHistory, 2)
        For i = 1 To UBound(forceHistory, 1)
            totInd = totInd + 1
            If i + 1 > UBound(forceHistory, 1) And j < UBound(forceHistory, 2) Then
                jmax = min(j + 1, UBound(forceHistory, 2))
                imax = 1
            Else
                jmax = j
                imax = min(i + 1, UBound(forceHistory, 1))
            End If
            If iB + 1 > UBound(forceHistory, 1) And jB < UBound(forceHistory, 2) Then
                jBmax = min(jB + 1, UBound(forceHistory, 2))
                iBmax = 1
            Else
                jBmax = jB
                iBmax = min(iB + 1, UBound(forceHistory, 1))
            End If
            For k = 0 To stepQTY - kOverlap - 1
                ' MoC
                If modDbl(k + (totInd - 1) * stepQTY, 2) = 0 Then
                    ' update even cells
                    vAv = arrayA(1, pipeSegQTY)
                    For n = 0 To pipeSegQTY - 1
                        vAv = vAv + arrayA(1, n)
                        vAv = vAv + arrayB(1, n)
                    Next
                    vAv = vAv / (2 * pipeSegQTY - 1)
                    If useUndamped Then
                        For m = 0 To 1
                            ' https://docs.aft.com/impulse/InfinitePipeTransientTheory.html
                            arrayA(m, 0) = 3 * arrayB(m, 0) - 3 * contA0(m, -2, 1) + contA0(m, -3, 2) - m * vAv
                            arrayA(m, pipeSegQTY) = 3 * arrayB(m, pipeSegQTY - 1) - 3 * contAN(m, -2, -1) + contAN(m, -3, -2) - m * vAv
                            
                            contA0(m, -2, 1) = contA0(m, 0, 1) - m * vAv
                            contA0(m, 0, 1) = arrayB(m, 0) - m * vAv
                            contA0(m, -3, 2) = contA0(m, -1, 2) - m * vAv
                            contA0(m, -1, 2) = arrayA(m, 1) - m * vAv
                            
                            contAN(m, -2, -1) = contAN(m, 0, -1) - m * vAv
                            contAN(m, 0, -1) = arrayB(m, pipeSegQTY - 1) - m * vAv
                            contAN(m, -3, -2) = contAN(m, -1, -2) - m * vAv
                            contAN(m, -1, -2) = arrayA(m, pipeSegQTY - 2) - m * vAv
                        Next
                    Else
                        arrayA(0, 0) = arrayB(0, 0) / dacayFactor
                        arrayA(0, pipeSegQTY) = arrayB(0, pipeSegQTY - 1) / dacayFactor
                        arrayA(1, 0) = arrayB(1, 0) - vAv
                        arrayA(1, pipeSegQTY) = arrayB(1, pipeSegQTY - 1) - vAv
                    End If
                    For n = 1 To pipeSegQTY - 1
                        dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                        arrayA(0, n) = (arrayB(0, n - 1) + arrayB(0, n)) / 2 + rhoC * (arrayB(1, n - 1) - arrayB(1, n)) / 2
                        arrayA(1, n) = dv - vAv + (arrayB(0, n - 1) - arrayB(0, n)) / (2 * rhoC) + (arrayB(1, n - 1) + arrayB(1, n)) / 2
                    Next
                    For n = 0 To pipeSegQTY - 1
                        dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                        arrayB(1, n) = dv - vAv + arrayB(1, n)
                    Next
                    dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayA(0, pivotSegQTY) + arrayA(0, pivotSegQTY - 1) - arrayA(0, pipeSegQTY - pivotSegQTY) - arrayA(0, pipeSegQTY - pivotSegQTY + 1)) / 2
                Else
                    ' update odd cells
                    For n = 0 To pipeSegQTY - 1
                        dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                        arrayB(0, n) = (arrayA(0, n) + arrayA(0, n + 1)) / 2 + rhoC * (arrayA(1, n) - arrayA(1, n + 1)) / 2
                        arrayB(1, n) = dv + (arrayA(0, n) - arrayA(0, n + 1)) / (2 * rhoC) + (arrayA(1, n) + arrayA(1, n + 1)) / 2
                    Next
                    For n = 1 To pipeSegQTY - 1
                        dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                        arrayA(1, n) = dv + arrayA(1, n)
                    Next
                    dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayB(0, pivotSegQTY) - arrayB(0, pipeSegQTY - pivotSegQTY))
                End If
                
                ' Kinematics
                forceA = forceHistory(i, j) * (1 - k / (stepQTY - 1)) + forceHistory(imax, jmax) * (k / (stepQTY - 1))
                forceB = forceHistory(iB, jB) * (1 - (k + kOverlap) / (stepQTY - 1)) + forceHistory(iBmax, jBmax) * ((k + kOverlap) / (stepQTY - 1))
            
                aNew = (dF + (forceA - forceB) - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
                If Abs(v) < fricAcc Then
                    vNew = (a + aNew) * dt / 2
                Else
                    vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
                End If
                x = x + (v + vNew) * dt / 2
                v = vNew
                a = aNew
                
                If Abs(a) > aMax Then
                    aMax = Abs(a)
                End If
                If Abs(v) > vMax Then
                    vMax = Abs(v)
                End If
                If Abs(x) > xMax Then
                    xMax = Abs(x)
                End If
                If Abs(forceA - forceB) > FMax Then
                    FMax = Abs(forceA - forceB)
                End If
            Next
            If iB + 1 > UBound(forceHistory, 1) And jB < UBound(forceHistory, 2) Then
                jB = min(jB + 1, UBound(forceHistory, 2))
                iB = 1
            Else
                iB = min(iB + 1, UBound(forceHistory, 1))
            End If
            If iB + 1 > UBound(forceHistory, 1) And jB < UBound(forceHistory, 2) Then
                jBmax = min(jB + 1, UBound(forceHistory, 2))
                iBmax = 1
            Else
                jBmax = jB
                iBmax = min(iB + 1, UBound(forceHistory, 1))
            End If
            For k = stepQTY - kOverlap To stepQTY - 1
                ' MoC
                If modDbl(k + (totInd - 1) * stepQTY, 2) = 0 Then
                    ' update even cells
                    vAv = arrayA(1, pipeSegQTY)
                    For n = 0 To pipeSegQTY - 1
                        vAv = vAv + arrayA(1, n)
                        vAv = vAv + arrayB(1, n)
                    Next
                    vAv = vAv / (2 * pipeSegQTY - 1)
                    If useUndamped Then
                        For m = 0 To 1
                            ' https://docs.aft.com/impulse/InfinitePipeTransientTheory.html
                            arrayA(m, 0) = 3 * arrayB(m, 0) - 3 * contA0(m, -2, 1) + contA0(m, -3, 2) - m * vAv
                            arrayA(m, pipeSegQTY) = 3 * arrayB(m, pipeSegQTY - 1) - 3 * contAN(m, -2, -1) + contAN(m, -3, -2) - m * vAv
                            
                            contA0(m, -2, 1) = contA0(m, 0, 1) - m * vAv
                            contA0(m, 0, 1) = arrayB(m, 0) - m * vAv
                            contA0(m, -3, 2) = contA0(m, -1, 2) - m * vAv
                            contA0(m, -1, 2) = arrayA(m, 1) - m * vAv
                            
                            contAN(m, -2, -1) = contAN(m, 0, -1) - m * vAv
                            contAN(m, 0, -1) = arrayB(m, pipeSegQTY - 1) - m * vAv
                            contAN(m, -3, -2) = contAN(m, -1, -2) - m * vAv
                            contAN(m, -1, -2) = arrayA(m, pipeSegQTY - 2) - m * vAv
                        Next
                    Else
                        arrayA(0, 0) = arrayB(0, 0) / dacayFactor
                        arrayA(0, pipeSegQTY) = arrayB(0, pipeSegQTY - 1) / dacayFactor
                        arrayA(1, 0) = arrayB(1, 0) - vAv
                        arrayA(1, pipeSegQTY) = arrayB(1, pipeSegQTY - 1) - vAv
                    End If
                    For n = 1 To pipeSegQTY - 1
                        dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                        arrayA(0, n) = (arrayB(0, n - 1) + arrayB(0, n)) / 2 + rhoC * (arrayB(1, n - 1) - arrayB(1, n)) / 2
                        arrayA(1, n) = dv - vAv + (arrayB(0, n - 1) - arrayB(0, n)) / (2 * rhoC) + (arrayB(1, n - 1) + arrayB(1, n)) / 2
                    Next
                    For n = 0 To pipeSegQTY - 1
                        dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                        arrayB(1, n) = dv - vAv + arrayB(1, n)
                    Next
                    dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayA(0, pivotSegQTY) + arrayA(0, pivotSegQTY - 1) - arrayA(0, pipeSegQTY - pivotSegQTY) - arrayA(0, pipeSegQTY - pivotSegQTY + 1)) / 2
                Else
                    ' update odd cells
                    For n = 0 To pipeSegQTY - 1
                        dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                        arrayB(0, n) = (arrayA(0, n) + arrayA(0, n + 1)) / 2 + rhoC * (arrayA(1, n) - arrayA(1, n + 1)) / 2
                        arrayB(1, n) = dv + (arrayA(0, n) - arrayA(0, n + 1)) / (2 * rhoC) + (arrayA(1, n) + arrayA(1, n + 1)) / 2
                    Next
                    For n = 1 To pipeSegQTY - 1
                        dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                        arrayA(1, n) = dv + arrayA(1, n)
                    Next
                    dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayB(0, pivotSegQTY) - arrayB(0, pipeSegQTY - pivotSegQTY))
                End If
                
                ' Kinematics
                forceA = forceHistory(i, j) * (1 - k / (stepQTY - 1)) + forceHistory(imax, jmax) * (k / (stepQTY - 1))
                forceB = forceHistory(iB, jB) * (1 - (k - stepQTY + kOverlap) / (stepQTY - 1)) + forceHistory(iBmax, jBmax) * ((k - stepQTY + kOverlap) / (stepQTY - 1))
            
                aNew = (dF + (forceA - forceB) - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
                If Abs(v) < fricAcc Then
                    vNew = (a + aNew) * dt / 2
                Else
                    vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
                End If
                x = x + (v + vNew) * dt / 2
                v = vNew
                a = aNew
                
                If Abs(a) > aMax Then
                    aMax = Abs(a)
                End If
                If Abs(v) > vMax Then
                    vMax = Abs(v)
                End If
                If Abs(x) > xMax Then
                    xMax = Abs(x)
                End If
                If Abs(forceA - forceB) > FMax Then
                    FMax = Abs(forceA - forceB)
                End If
            Next
            If outputType > 0 Then
                If outputType = 1 Then
                    resultArray(totInd) = x
                ElseIf outputType = 2 Then
                    resultArray(totInd) = v
                ElseIf outputType = 3 Then
                    resultArray(totInd) = a
                End If
            End If
        Next
    Next
    xZero = x
    Do While x * xZero > 0.01
        totInd = totInd + 1
        For k = 1 To stepQTY
            ' MoC
            If modDbl(k + (totInd - 1) * stepQTY, 2) = 0 Then
                ' update even cells
                vAv = arrayA(1, pipeSegQTY)
                For n = 0 To pipeSegQTY - 1
                    vAv = vAv + arrayA(1, n)
                    vAv = vAv + arrayB(1, n)
                Next
                vAv = vAv / (2 * pipeSegQTY - 1)
                If useUndamped Then
                    For m = 0 To 1
                        ' https://docs.aft.com/impulse/InfinitePipeTransientTheory.html
                        arrayA(m, 0) = 3 * arrayB(m, 0) - 3 * contA0(m, -2, 1) + contA0(m, -3, 2) - m * vAv
                        arrayA(m, pipeSegQTY) = 3 * arrayB(m, pipeSegQTY - 1) - 3 * contAN(m, -2, -1) + contAN(m, -3, -2) - m * vAv
                        
                        contA0(m, -2, 1) = contA0(m, 0, 1) - m * vAv
                        contA0(m, 0, 1) = arrayB(m, 0) - m * vAv
                        contA0(m, -3, 2) = contA0(m, -1, 2) - m * vAv
                        contA0(m, -1, 2) = arrayA(m, 1) - m * vAv
                        
                        contAN(m, -2, -1) = contAN(m, 0, -1) - m * vAv
                        contAN(m, 0, -1) = arrayB(m, pipeSegQTY - 1) - m * vAv
                        contAN(m, -3, -2) = contAN(m, -1, -2) - m * vAv
                        contAN(m, -1, -2) = arrayA(m, pipeSegQTY - 2) - m * vAv
                    Next
                Else
                    arrayA(0, 0) = arrayB(0, 0) / dacayFactor
                    arrayA(0, pipeSegQTY) = arrayB(0, pipeSegQTY - 1) / dacayFactor
                    arrayA(1, 0) = arrayB(1, 0) - vAv
                    arrayA(1, pipeSegQTY) = arrayB(1, pipeSegQTY - 1) - vAv
                End If
                For n = 1 To pipeSegQTY - 1
                    dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                    arrayA(0, n) = (arrayB(0, n - 1) + arrayB(0, n)) / 2 + rhoC * (arrayB(1, n - 1) - arrayB(1, n)) / 2
                    arrayA(1, n) = dv - vAv + (arrayB(0, n - 1) - arrayB(0, n)) / (2 * rhoC) + (arrayB(1, n - 1) + arrayB(1, n)) / 2
                Next
                For n = 0 To pipeSegQTY - 1
                    dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                    arrayB(1, n) = dv - vAv + arrayB(1, n)
                Next
                dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayA(0, pivotSegQTY) + arrayA(0, pivotSegQTY - 1) - arrayA(0, pipeSegQTY - pivotSegQTY) - arrayA(0, pipeSegQTY - pivotSegQTY + 1)) / 2
            Else
                ' update odd cells
                For n = 0 To pipeSegQTY - 1
                    dv = a * dt * interpFractionB(n, pivotSegQTY, pipeSegQTY)
                    arrayB(0, n) = (arrayA(0, n) + arrayA(0, n + 1)) / 2 + rhoC * (arrayA(1, n) - arrayA(1, n + 1)) / 2
                    arrayB(1, n) = dv + (arrayA(0, n) - arrayA(0, n + 1)) / (2 * rhoC) + (arrayA(1, n) + arrayA(1, n + 1)) / 2
                Next
                For n = 1 To pipeSegQTY - 1
                    dv = a * dt * interpFractionA(n, pivotSegQTY, pipeSegQTY)
                    arrayA(1, n) = dv + arrayA(1, n)
                Next
                dF = (dampingA) * dF + (1 - dampingA) * fluidArea * (arrayB(0, pivotSegQTY) - arrayB(0, pipeSegQTY - pivotSegQTY))
            End If
            
            ' Kinematics
            aNew = (dF - (minUnsigned(gap, x) + max(0, Abs(x) - gap) * sign(x) * (restrainFreqRatio ^ 2)) * stiffness - v * damping) / mass
            If Abs(v) < fricAcc Then
                vNew = (a + aNew) * dt / 2
            Else
                vNew = v + (a + aNew) * dt / 2 - sign(v, 0.000001) * fricAcc
            End If
            x = x + (v + vNew) * dt / 2
            v = vNew
            a = aNew
            
            If Abs(a) > aMax Then
                aMax = Abs(a)
            End If
            If Abs(v) > vMax Then
                vMax = Abs(v)
            End If
            If Abs(x) > xMax Then
                xMax = Abs(x)
            End If
            
            If x * xZero <= 0.01 Then
                xZero = 0
            End If
        Next
        If outputType > 0 Then
            If totInd <= outMax * 2 Then
                If outputType = 1 Then
                    resultArray(totInd) = x
                ElseIf outputType = 2 Then
                    resultArray(totInd) = v
                ElseIf outputType = 3 Then
                    resultArray(totInd) = a
                End If
            End If
        End If
    Loop
    
    If outputType = 0 Then
        ReDim resultArray(0 To 4) As Double
        resultArray(0) = Abs(minUnsigned(gap, xMax) + max(0, Abs(xMax) - gap) * sign(xMax) * (restrainFreqRatio ^ 2)) * stiffness ' max static equivalent
        resultArray(1) = xMax ' max displacement
        resultArray(2) = vMax ' max velocity
        resultArray(3) = aMax ' max acceloration
        resultArray(4) = FMax ' max applied force
    End If
    
    GetPeakResponseJC = resultArray
    Exit Function
ErrFound:
    rhoC = rhoC
End Function
