"""3D milk into coffee inside the real mug (snappyHexMesh + twoLiquidMixingFoam).

Domain: the coffee in the mug up to the level after the pour (6.6 cm). The milk stream from the jug lands at
x = 3.05 cm with (-0.284, 0, -1.05) m/s (projectile from the jug lip), radius 2.4 mm, ~20 mL/s for 1.2 s.
Milk 5 C (1033 kg/m3, 2.9 mPa s), coffee 80 C (975 kg/m3, 0.355 mPa s).
    python mk_milk3d.py CASE [BG_MM] [LEVEL]
"""
import os, sys, shutil
C = sys.argv[1]; BG = float(sys.argv[2]) * 1e-3 if len(sys.argv) > 2 else 2e-3; LEV = int(sys.argv[3]) if len(sys.argv) > 3 else 1
H = 0.066; U = (-0.284, 0.0, -1.05); INL = (0.0305, 0.0, H); R_IN = 0.0024; OUTL = (-0.034, 0.0, H); R_OUT = 0.005
T_OFF, END = 3.0, 4.0
HDR = "FoamFile {{ version 2.0; format ascii; class {cls}; {loc}object {obj}; }}\n"
def write(p, body, cls='dictionary', loc=''):
    f = os.path.join(C, p); os.makedirs(os.path.dirname(f), exist_ok=True)
    open(f, 'w').write(HDR.format(cls=cls, obj=os.path.basename(p), loc=f'location "{loc}"; ' if loc else '') + body)
n = lambda a, b: max(4, round((b - a) / BG))
os.makedirs(f'{C}/constant/triSurface', exist_ok=True)
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geometry', 'mug.stl'), f'{C}/constant/triSurface/mug.stl')
X0, X1, Z0 = -0.0405, 0.0405, -0.001
write('system/blockMeshDict', f"""
convertToMeters 1;
vertices ( ({X0} {X0} {Z0}) ({X1} {X0} {Z0}) ({X1} {X1} {Z0}) ({X0} {X1} {Z0}) ({X0} {X0} {H}) ({X1} {X0} {H}) ({X1} {X1} {H}) ({X0} {X1} {H}) );
blocks ( hex (0 1 2 3 4 5 6 7) ({n(X0, X1)} {n(X0, X1)} {n(Z0, H)}) simpleGrading (1 1 1) );
edges ();
boundary
(
    surface {{ type patch; faces ( (4 5 6 7) ); }}
    box     {{ type wall;  faces ( (0 3 2 1) (0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2) ); }}
);
""")
write('system/snappyHexMeshDict', f"""
castellatedMesh true; snap true; addLayers false;
geometry
{{
    mug.stl {{ type triSurfaceMesh; name mug; }}
    jet     {{ type searchableBox; min (0.010 -0.008 0.030); max (0.037 0.008 0.067); }}
}}
castellatedMeshControls
{{
    maxLocalCells 2000000; maxGlobalCells 4000000; minRefinementCells 0; maxLoadUnbalance 0.1; nCellsBetweenLevels 2;
    features ();
    refinementSurfaces {{ mug {{ level (0 0); }} }}
    resolveFeatureAngle 30;
    refinementRegions {{ jet {{ mode inside; levels ((1e15 {LEV})); }} }}
    locationInMesh (0.0 0.0 0.03);
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
    {{ name inletFaces;  type faceSet; action new;    source patchToFace; patch surface; }}
    {{ name inletFaces;  type faceSet; action subset; source sphereToFace; origin ({INL[0]} {INL[1]} {INL[2]}); radius {R_IN}; }}
    {{ name outletFaces; type faceSet; action new;    source patchToFace; patch surface; }}
    {{ name outletFaces; type faceSet; action subset; source sphereToFace; origin ({OUTL[0]} {OUTL[1]} {OUTL[2]}); radius {R_OUT}; }}
);
""")
write('system/createPatchDict', """
pointSync false;
patches
(
    { name inlet;  patchInfo { type patch; } constructFrom set; set inletFaces; }
    { name outlet; patchInfo { type patch; } constructFrom set; set outletFaces; }
);
""")
write('constant/transportProperties', """
Dab 1e-9;
alphatab 1;
phases (milk coffee);
milk   { transportModel Newtonian; nu 2.8074e-06; rho 1033; }
coffee { transportModel Newtonian; nu 3.6410e-07; rho 975; }
""")
write('constant/g', "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n", cls='uniformDimensionedVectorField', loc='constant')
write('constant/turbulenceProperties', "simulationType laminar;\n")
ut = lambda s: f"({s * U[0]:.4f} {s * U[1]:.4f} {s * U[2]:.4f})"
utab = f"( (0 {ut(0)}) (0.05 {ut(1)}) ({T_OFF} {ut(1)}) ({T_OFF + 0.05} {ut(0)}) (100 {ut(0)}) )"
def field(name, dims, internal, bcs, cls='volScalarField'):
    body = f"dimensions {dims};\ninternalField uniform {internal};\nboundaryField\n{{\n" + ''.join(f"    {p} {{ {b} }}\n" for p, b in bcs.items()) + "}\n"
    write(f'0.orig/{name}', body, cls=cls, loc='0')
field('U', '[0 1 -1 0 0 0 0]', '(0 0 0)', {'mug': 'type noSlip;', 'box': 'type noSlip;', 'surface': 'type slip;',
      'inlet': f'type uniformFixedValue; uniformValue {{ type table; values {utab}; }} value uniform (0 0 0);',
      'outlet': 'type pressureInletOutletVelocity; value uniform (0 0 0);'}, cls='volVectorField')
field('alpha.milk', '[0 0 0 0 0 0 0]', 0, {'mug': 'type zeroGradient;', 'box': 'type zeroGradient;', 'surface': 'type zeroGradient;',
      'inlet': 'type fixedValue; value uniform 1;', 'outlet': 'type inletOutlet; inletValue uniform 0; value uniform 0;'})
field('p_rgh', '[1 -1 -2 0 0 0 0]', 0, {'mug': 'type fixedFluxPressure; value uniform 0;', 'box': 'type fixedFluxPressure; value uniform 0;',
      'surface': 'type fixedFluxPressure; value uniform 0;', 'inlet': 'type fixedFluxPressure; value uniform 0;',
      'outlet': 'type fixedValue; value uniform 0;'})
write('system/controlDict', f"""
application twoLiquidMixingFoam;
startFrom latestTime; startTime 0; stopAt endTime; endTime {END};
deltaT 1e-4; writeControl adjustable; writeInterval {1/24:.8f};
purgeWrite 0; writeFormat ascii; writePrecision 8; writeCompression off;
timeFormat general; timePrecision 6; runTimeModifiable yes;
adjustTimeStep on; maxCo 0.5; maxAlphaCo 0.5; maxDeltaT 2e-3;
""")
write('system/fvSchemes', """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(rhoPhi,U) Gauss linearUpwind grad(U);
    div(phi,alpha) Gauss vanLeer;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited corrected 0.5; }
""")
write('system/fvSolution', """
solvers
{
    "alpha.milk.*" { nAlphaSubCycles 2; nAlphaCorr 1; solver smoothSolver; smoother GaussSeidel; tolerance 1e-9; relTol 0; nSweeps 1; }
    p_rgh      { solver GAMG; tolerance 1e-7; relTol 0.01; smoother GaussSeidel; }
    p_rghFinal { $p_rgh; relTol 0; }
    U          { solver smoothSolver; smoother GaussSeidel; tolerance 1e-7; relTol 0.1; nSweeps 1; }
    UFinal     { $U; relTol 0; }
}
PIMPLE { momentumPredictor yes; nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 1; }
""")
write('system/decomposeParDict', "numberOfSubdomains 2;\nmethod scotch;\n")
print('case written:', C)
