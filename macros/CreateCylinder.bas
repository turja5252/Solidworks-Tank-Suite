' Created by Tanzim Nasir
' Copyright (c) 2026 Elite Integrity Services.
' Run from inside SolidWorks: Tools > Macro > Run (or a toolbar button).
' Works with SolidWorks 2013 and newer. Units: inches. API lengths are meters.

Option Explicit

Sub main()
    Dim swApp As SldWorks.SldWorks
    Dim swModel As ModelDoc2
    Dim swSketchMgr As SketchManager
    Dim swFeatMgr As FeatureManager
    Dim feat As Object
    Dim latestFeat As Feature
    Dim diaStr As String
    Dim htStr As String
    Dim diameterIn As Double
    Dim heightIn As Double
    Dim radiusM As Double
    Dim heightM As Double
    Dim template As String
    Dim ok As Boolean

    Set swApp = Application.SldWorks
    If swApp Is Nothing Then
        MsgBox "SolidWorks application was not found.", vbExclamation, "Create Cylinder"
        Exit Sub
    End If

    diaStr = InputBox("Diameter (inches):", "Create Cylinder", "24")
    If Trim$(diaStr) = "" Then Exit Sub
    htStr = InputBox("Height (inches):", "Create Cylinder", "48")
    If Trim$(htStr) = "" Then Exit Sub

    diameterIn = Val(diaStr)
    heightIn = Val(htStr)
    If diameterIn <= 0# Or heightIn <= 0# Then
        MsgBox "Diameter and height must be greater than zero.", vbExclamation, "Create Cylinder"
        Exit Sub
    End If

    radiusM = (diameterIn * 0.0254) / 2#
    heightM = heightIn * 0.0254

    template = swApp.GetUserPreferenceStringValue(swUserPreferenceStringValue_e.swDefaultTemplatePart)
    If Len(Trim$(template)) > 0 Then
        Set swModel = swApp.NewDocument(template, 0, 0, 0)
    End If
    If swModel Is Nothing Then
        Set swModel = swApp.NewPart
    End If
    If swModel Is Nothing Then
        MsgBox "Could not create a new part." & vbCrLf & _
               "In SolidWorks: Tools > Options > Default Templates," & vbCrLf & _
               "set a Part template (.prtdot), then run this again.", _
               vbExclamation, "Create Cylinder"
        Exit Sub
    End If

    ok = swModel.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
    If Not ok Then
        ok = swModel.Extension.SelectByID2("Plane1", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
    End If
    If Not ok Then
        MsgBox "Could not select the Front Plane.", vbExclamation, "Create Cylinder"
        Exit Sub
    End If

    Set swSketchMgr = swModel.SketchManager
    swSketchMgr.InsertSketch True
    If swSketchMgr.CreateCircleByRadius(0#, 0#, 0#, radiusM) Is Nothing Then
        MsgBox "Could not create the circle sketch.", vbExclamation, "Create Cylinder"
        Exit Sub
    End If
    swModel.ClearSelection2 True
    swSketchMgr.InsertSketch True

    Set latestFeat = swModel.FeatureByPositionReverse(0)
    If Not latestFeat Is Nothing Then
        latestFeat.Select2 False, 0
    End If

    Set swFeatMgr = swModel.FeatureManager
    Set feat = ExtrudeBlind(swFeatMgr, heightM)
    If feat Is Nothing Then
        MsgBox "Extrude failed.", vbExclamation, "Create Cylinder"
        Exit Sub
    End If

    swModel.ViewZoomtofit2
    MsgBox "Created cylinder" & vbCrLf & _
           "Diameter: " & CStr(diameterIn) & " in" & vbCrLf & _
           "Height: " & CStr(heightIn) & " in", _
           vbInformation, "Create Cylinder"
End Sub

Private Function ExtrudeBlind(swFeatMgr As FeatureManager, heightM As Double) As Object
    Dim feat As Object

    ' Newer SolidWorks FeatureExtrusion2 (includes start condition args).
    On Error Resume Next
    Set feat = swFeatMgr.FeatureExtrusion2( _
        True, False, False, _
        0, 0, _
        heightM, 0#, _
        False, False, False, False, _
        0#, 0#, _
        False, False, False, False, _
        True, True, True, _
        0, 0#, False)
    If feat Is Nothing Then
        ' SolidWorks 2013 FeatureExtrusion2.
        Set feat = swFeatMgr.FeatureExtrusion2( _
            True, False, False, _
            0, 0, _
            heightM, 0#, _
            False, False, False, False, _
            0#, 0#, _
            False, False, False, False, _
            True, True, True)
    End If
    On Error GoTo 0

    Set ExtrudeBlind = feat
End Function
