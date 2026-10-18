"""3D coffee pour into the real mug geometry (snappyHexMesh + interFoam).

Stream: leaves the pot spout at P_TIP = (-3, 0, 13) cm with 0.5 m/s at 36 deg below horizontal (from models.py),
radius 5 mm, for 3 s. Mug initially filled to 5.2 cm. Coffee 975 kg/m3 (80 C), air.
    python mk_pour3d.py CASE [BG_MM] [LEVEL]      default: 4 mm background, one refinement level (2 mm)
"""
import os, sys, shutil
C = sys.argv[1]; BG = float(sys.argv[2]) * 1e-3 if len(sys.argv) > 2 else 4e-3; LEV = int(sys.argv[3]) if len(sys.argv) > 3 else 1
U = (0.566, 0.0, -0.413); TIP = (-0.045, 0.0, 0.130); R_JET = 0.008; T_OFF, END = 4.0, 4.6; LEVEL0 = -1.0   # empty mug
X0, X1, Y0, Y1, Z0, Z1 = -0.060, 0.060, -0.055, 0.055, -0.006, 0.130
HDR = "FoamFile {{ version 2.0; format ascii; class {cls}; {loc}object {obj}; }}\n"
def write(p, body, cls='dictionary', loc=''):
    f = os.path.join(C, p); os.makedirs(os.path.dirname(f), exist_ok=True)
    open(f, 'w').write(HDR.format(cls=cls, obj=os.path.basename(p), loc=f'location "{loc}"; ' if loc else '') + body)
n = lambda a, b: max(4, round((b - a) / BG))
os.makedirs(f'{C}/constant/triSurface', exist_ok=True)
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geometry', 'mug.stl'), f'{C}/constant/triSurface/mug.stl')

write('system/blockMeshDict', f"""
convertToMeters 1;
vertices ( ({X0} {Y0} {Z0}) ({X1} {Y0} {Z0}) ({X1} {Y1} {Z0}) ({X0} {Y1} {Z0}) ({X0} {Y0} {Z1}) ({X1} {Y0} {Z1}) ({X1} {Y1} {Z1}) ({X0} {Y1} {Z1}) );
blocks ( hex (0 1 2 3 4 5 6 7) ({n(X0, X1)} {n(Y0, Y1)} {n(Z0, Z1)}) simpleGrading (1 1 1) );
edges ();
boundary
(
    table      {{ type wall;  faces ( (0 3 2 1) ); }}
    atmosphere {{ type patch; faces ( (4 5 6 7) (0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2) ); }}
);
""")
lv = f"({LEV} {LEV})"
write('system/snappyHexMeshDict', f"""
castellatedMesh true; snap true; addLayers false;
geometry
{{
    mug.stl {{ type triSurfaceMesh; name mug; }}
    stream  {{ type searchableBox; min (-0.054 -0.013 0.0); max (0.035 0.013 0.131); }}
    surf    {{ type searchableCylinder; point1 (0 0 0.025); point2 (0 0 0.072); radius 0.041; }}
}}
castellatedMeshControls
{{
    maxLocalCells 2000000; maxGlobalCells 4000000; minRefinementCells 0; maxLoadUnbalance 0.1; nCellsBetweenLevels 2;
    features ();
    refinementSurfaces {{ mug {{ level {lv}; }} }}
    resolveFeatureAngle 30;
    refinementRegions {{ stream {{ mode inside; levels ((1e15 {LEV})); }} surf {{ mode inside; levels ((1e15 {LEV})); }} }}
    locationInMesh (0.0 0.0 0.06);
    allowFreeStandingZoneFaces true;
}}
snapControls {{ nSmoothPatch 3; tolerance 2.0; nSolveIter 50; nRelaxIter 5; nFeatureSnapIter 10; implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap false; }}
addLayersControls {{ relativeSizes true; layers {{ }} expansionRatio 1.0; finalLayerThickness 0.3; minThickness 0.1; nGrow 0;
    featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10; maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50; }}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-13; minTetQuality 1e-15;
    minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.05; minVolRatio 0.01; minTriangleTwist -1;
    nSmoothScale 4; errorReduction 0.75;
}}
mergeTolerance 1e-6;
""")
write('system/topoSetDict', f"""
actions
(
    {{ name inletFaces; type faceSet; action new; source patchToFace; patch atmosphere; }}
    {{ name inletFaces; type faceSet; action subset; source sphereToFace; origin ({TIP[0]} {TIP[1]} {TIP[2]}); radius {R_JET}; }}
);
""")
write('system/createPatchDict', """
pointSync false;
patches ( { name inlet; patchInfo { type patch; } constructFrom set; set inletFaces; } );
""")
write('constant/transportProperties', """
phases (coffee air);
coffee { transportModel Newtonian; nu 3.64e-07; rho 975; }
air    { transportModel Newtonian; nu 1.6e-05;  rho 1.1; }
sigma 0.063;
""")
write('constant/g', "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n", cls='uniformDimensionedVectorField', loc='constant')
write('constant/turbulenceProperties', "simulationType laminar;\n")
ut = lambda s: f"({s * U[0]:.4f} {s * U[1]:.4f} {s * U[2]:.4f})"
utab = f"( (0 {ut(0)}) (0.05 {ut(1)}) ({T_OFF} {ut(1)}) ({T_OFF + 0.05} {ut(0)}) (100 {ut(0)}) )"
def field(name, dims, internal, bcs, cls='volScalarField'):
    body = f"dimensions {dims};\ninternalField uniform {internal};\nboundaryField\n{{\n" + ''.join(f"    {p} {{ {b} }}\n" for p, b in bcs.items()) + "}\n"
    write(f'0.orig/{name}', body, cls=cls, loc='0')
field('U', '[0 1 -1 0 0 0 0]', '(0 0 0)', {'table': 'type noSlip;', 'mug': 'type noSlip;',
      'inlet': f'type uniformFixedValue; uniformValue {{ type table; values {utab}; }} value uniform (0 0 0);',
      'atmosphere': 'type pressureInletOutletVelocity; value uniform (0 0 0);'}, cls='volVectorField')
field('alpha.coffee', '[0 0 0 0 0 0 0]', 0, {'table': 'type zeroGradient;', 'mug': 'type zeroGradient;',
      'inlet': f'type uniformFixedValue; uniformValue {{ type table; values ( (0 1) ({T_OFF} 1) ({T_OFF + 0.05} 0) (100 0) ); }} value uniform 0;',
      'atmosphere': 'type inletOutlet; inletValue uniform 0; value uniform 0;'})
field('p_rgh', '[1 -1 -2 0 0 0 0]', 0, {'table': 'type fixedFluxPressure; value uniform 0;', 'mug': 'type fixedFluxPressure; value uniform 0;',
      'inlet': 'type fixedFluxPressure; value uniform 0;', 'atmosphere': 'type totalPressure; p0 uniform 0; value uniform 0;'})
write('system/setFieldsDict', f"""
defaultFieldValues ( volScalarFieldValue alpha.coffee 0 );
regions ( cylinderToCell {{ p1 (0 0 -0.01); p2 (0 0 {LEVEL0}); radius 0.0405; fieldValues ( volScalarFieldValue alpha.coffee 1 ); }} );
""")
write('system/controlDict', f"""
application interFoam;
startFrom latestTime; startTime 0; stopAt endTime; endTime {END};
deltaT 1e-5; writeControl adjustable; writeInterval {1/24:.8f};
purgeWrite 0; writeFormat binary; writePrecision 6; writeCompression off;
timeFormat general; timePrecision 6; runTimeModifiable yes;
adjustTimeStep yes; maxCo 0.5; maxAlphaCo 0.5; maxDeltaT 1e-3;
functions
{{
    liquidSurface
    {{
        type surfaces; libs (sampling); writeControl adjustableRunTime; writeInterval {1/24:.8f};
        surfaceFormat stl; fields (alpha.coffee); interpolationScheme cellPoint;
        surfaces {{ coffee {{ type isoSurface; isoField alpha.coffee; isoValue 0.5; interpolate true; regularise diagcell; }} }}
    }}
}}
""")
write('system/fvSchemes', """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes
{
    div(rhoPhi,U) Gauss linearUpwind grad(U);
    div(phi,alpha) Gauss vanLeer;
    div(phirb,alpha) Gauss linear;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited corrected 0.5; }
""")
write('system/fvSolution', """
solvers
{
    "alpha.coffee.*" { nAlphaCorr 2; nAlphaSubCycles 1; cAlpha 1; MULESCorr yes; nLimiterIter 5;
                       solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }
    "pcorr.*"   { solver PCG; preconditioner DIC; tolerance 1e-5; relTol 0; }
    p_rgh       { solver GAMG; smoother DIC; tolerance 1e-7; relTol 0.05; }
    p_rghFinal  { $p_rgh; relTol 0; }
    U           { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-6; relTol 0; }
}
PIMPLE { momentumPredictor no; nOuterCorrectors 1; nCorrectors 3; nNonOrthogonalCorrectors 1; }
relaxationFactors { equations { ".*" 1; } }
""")
write('system/decomposeParDict', "numberOfSubdomains 2;\nmethod scotch;\n")
print('case written:', C, 'background', BG * 1e3, 'mm, level', LEV)
