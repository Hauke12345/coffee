"""3D steam over the mug for the whole film (rhoReactingBuoyantFoam, no reactions), one-way coupled to the
cached coffee simulations: cells occupied by coffee (cellZone 'coffee', updated by run_steam3d.py) are held at
the 70 C surface temperature, saturated with vapour and at rest. Room air 22 C / 40 % RH with a gentle, slowly
varying draught (2-3 cm/s) entering from the -x side.
    python mk_steam3d.py CASE
"""
import os, sys, shutil
C = sys.argv[1]
SRC = os.path.dirname(os.path.abspath(__file__))   # thermo/ holds humid-air thermophysics (H2O, O2, N2; no reactions)
X0, X1, Y0, Y1, Z0, Z1 = -0.10, 0.13, -0.10, 0.10, -0.006, 0.30
BG = 5e-3
T_SURF, Y_SURF, T_AIR, Y_AIR = 343.15, 0.216788, 295.15, 0.0065625
YO2_AIR, YO2_SURF = 0.233 * (1 - Y_AIR), 0.233 * (1 - Y_SURF)
P0 = 101325.0
HDR = "FoamFile {{ version 2.0; format ascii; class {cls}; {loc}object {obj}; }}\n"
def write(p, body, cls='dictionary', loc=''):
    f = os.path.join(C, p); os.makedirs(os.path.dirname(f), exist_ok=True)
    open(f, 'w').write(HDR.format(cls=cls, obj=os.path.basename(p), loc=f'location "{loc}"; ' if loc else '') + body)
n = lambda a, b: max(4, round((b - a) / BG))
os.makedirs(f'{C}/constant/triSurface', exist_ok=True)
for f in ('thermo.compressibleGas', 'reactions', 'thermophysicalProperties', 'chemistryProperties', 'combustionProperties',
          'turbulenceProperties', 'g', 'hRef'):
    shutil.copy(os.path.join(SRC, 'thermo', f), os.path.join(C, 'constant', f))
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'geometry', 'mug.stl'), f'{C}/constant/triSurface/mug.stl')

write('system/blockMeshDict', f"""
convertToMeters 1;
vertices ( ({X0} {Y0} {Z0}) ({X1} {Y0} {Z0}) ({X1} {Y1} {Z0}) ({X0} {Y1} {Z0}) ({X0} {Y0} {Z1}) ({X1} {Y0} {Z1}) ({X1} {Y1} {Z1}) ({X0} {Y1} {Z1}) );
blocks ( hex (0 1 2 3 4 5 6 7) ({n(X0, X1)} {n(Y0, Y1)} {n(Z0, Z1)}) simpleGrading (1 1 1) );
edges ();
boundary
(
    table   {{ type wall;  faces ( (0 3 2 1) ); }}
    draft   {{ type patch; faces ( (0 4 7 3) ); }}
    ambient {{ type patch; faces ( (4 5 6 7) (1 2 6 5) (0 1 5 4) (3 7 6 2) ); }}
);
""")
write('system/snappyHexMeshDict', """
castellatedMesh true; snap true; addLayers false;
geometry
{
    mug.stl { type triSurfaceMesh; name mug; }
    plume   { type searchableCylinder; point1 (0.005 0 -0.005); point2 (0.02 0 0.14); radius 0.05; }
}
castellatedMeshControls
{
    maxLocalCells 3000000; maxGlobalCells 6000000; minRefinementCells 0; maxLoadUnbalance 0.1; nCellsBetweenLevels 2;
    features ();
    refinementSurfaces { mug { level (1 1); } }
    resolveFeatureAngle 30;
    refinementRegions { plume { mode inside; levels ((1e15 1)); } }
    locationInMesh (0.0 0.0 0.05);
    allowFreeStandingZoneFaces true;
}
snapControls { nSmoothPatch 3; tolerance 2.0; nSolveIter 50; nRelaxIter 5; nFeatureSnapIter 10; implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap false; }
addLayersControls { relativeSizes true; layers { } expansionRatio 1.0; finalLayerThickness 0.3; minThickness 0.1; nGrow 0;
    featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10; maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50; }
meshQualityControls
{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-13; minTetQuality 1e-15;
    minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.05; minVolRatio 0.01; minTriangleTwist -1;
    nSmoothScale 4; errorReduction 0.75;
}
mergeTolerance 1e-6;
""")
# gentle draught: slowly varying speed and direction
dr = [(0, 0.020, 0.000), (1.5, 0.030, 0.008), (3.0, 0.016, -0.006), (4.5, 0.028, 0.004), (6.0, 0.021, -0.010),
      (7.5, 0.032, 0.006), (9.0, 0.018, 0.000), (10.5, 0.027, -0.007), (12.0, 0.022, 0.005), (100, 0.022, 0.005)]
dtab = ' '.join(f'({t} ({u} {v} 0))' for t, u, v in dr)
def field(name, dims, internal, bcs, cls='volScalarField'):
    body = f"dimensions {dims};\ninternalField uniform {internal};\nboundaryField\n{{\n" + ''.join(f"    {p} {{ {b} }}\n" for p, b in bcs.items()) + "}\n"
    write(f'0.orig/{name}', body, cls=cls, loc='0')
op = lambda v: f'type inletOutlet; inletValue uniform {v}; value uniform {v};'
fx = lambda v: f'type fixedValue; value uniform {v};'
field('U', '[0 1 -1 0 0 0 0]', '(0.02 0 0)', {'table': 'type noSlip;', 'mug': 'type noSlip;',
      'draft': f'type uniformFixedValue; uniformValue {{ type table; values ( {dtab} ); }} value uniform (0.02 0 0);',
      'ambient': 'type pressureInletOutletVelocity; value uniform (0 0 0);'}, cls='volVectorField')
field('T', '[0 0 0 1 0 0 0]', T_AIR, {'table': 'type zeroGradient;', 'mug': 'type zeroGradient;', 'draft': fx(T_AIR), 'ambient': op(T_AIR)})
field('H2O', '[0 0 0 0 0 0 0]', Y_AIR, {'table': 'type zeroGradient;', 'mug': 'type zeroGradient;', 'draft': fx(Y_AIR), 'ambient': op(Y_AIR)})
field('O2', '[0 0 0 0 0 0 0]', YO2_AIR, {'table': 'type zeroGradient;', 'mug': 'type zeroGradient;', 'draft': fx(YO2_AIR), 'ambient': op(YO2_AIR)})
field('N2', '[0 0 0 0 0 0 0]', 1 - Y_AIR - YO2_AIR, {'table': 'type zeroGradient;', 'mug': 'type zeroGradient;',
      'draft': fx(1 - Y_AIR - YO2_AIR), 'ambient': op(1 - Y_AIR - YO2_AIR)})
field('Ydefault', '[0 0 0 0 0 0 0]', 0, {'table': 'type zeroGradient;', 'mug': 'type zeroGradient;', 'draft': fx(0), 'ambient': op(0)})
field('p_rgh', '[1 -1 -2 0 0 0 0]', P0, {'table': f'type fixedFluxPressure; value uniform {P0};', 'mug': f'type fixedFluxPressure; value uniform {P0};',
      'draft': f'type fixedFluxPressure; value uniform {P0};', 'ambient': f'type totalPressure; p0 uniform {P0}; value uniform {P0};'})
field('p', '[1 -1 -2 0 0 0 0]', P0, {k: f'type calculated; value uniform {P0};' for k in ('table', 'mug', 'draft', 'ambient')})
write('constant/fvOptions', f"""
coffeeT {{ type fixedTemperatureConstraint; selectionMode cellZone; cellZone coffee; mode uniform; temperature constant {T_SURF}; }}
coffeeY {{ type scalarFixedValueConstraint; selectionMode cellZone; cellZone coffee; fieldValues {{ H2O {Y_SURF}; O2 {YO2_SURF}; }} }}
coffeeU {{ type vectorFixedValueConstraint; selectionMode cellZone; cellZone coffee; fieldValues {{ U (0 0 0); }} }}
""")
write('system/controlDict', f"""
application rhoReactingBuoyantFoam;
startFrom latestTime; startTime 0; stopAt endTime; endTime 0.1;
deltaT 1e-3; writeControl adjustableRunTime; writeInterval {1/24:.8f};
purgeWrite 0; writeFormat binary; writePrecision 8; writeCompression off;
timeFormat general; timePrecision 6; runTimeModifiable yes;
adjustTimeStep yes; maxCo 0.6; maxDeltaT 5e-3;
""")
write('system/fvSchemes', """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) Gauss limitedLinearV 1;
    div(phi,Yi_h) Gauss limitedLinear01 1;
    div(phi,K) Gauss linear;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited corrected 0.5; }
fluxRequired { default no; p_rgh; }
""")
write('system/fvSolution', """
solvers
{
    "rho.*"     { solver diagonal; }
    p_rgh       { solver GAMG; smoother GaussSeidel; tolerance 2e-6; relTol 0.02; maxIter 50; }
    p_rghFinal  { $p_rgh; relTol 0; maxIter 100; }
    "(U|h|Yi)"  { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0.01; }
    "(U|h|Yi)Final" { $U; relTol 0; }
    "Yi.*"      { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0; }
}
PIMPLE { momentumPredictor yes; nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 1; }
""")
write('system/decomposeParDict', "numberOfSubdomains 2;\nmethod scotch;\n")
print('steam3d case written:', C)
