# Tablas del .DB de AutoPIPE usadas en la auditoria

## Contenido
- Como abrirlo
- Tablas y columnas
- Unidades

## Como abrirlo
SQLite. Abrir siempre en modo solo lectura: `sqlite3.connect('file:RUTA?mode=ro', uri=True)`. Si el archivo esta en una carpeta sincronizada o en uso, copiarlo a una carpeta de trabajo y abrir la copia. El `.DB` incluye tablas de resultados muy grandes (fuerzas, desplazamientos, cumplimiento de codigo) que la auditoria no necesita.

## Tablas y columnas
| Tabla | Columnas usadas | Para que |
|---|---|---|
| `Model_Info` | `Model_Name`, `Piping_Code`, `Edition`, `Material_Library`, `Model_Revision`, `Ambient_Temperature` | Identidad del modelo |
| `Static_Analysis` | `Analysis_Set_Number`, `Description`, `Analysis_Date`, `Analysis_Time`, `Contents_Weight_Included` (Yes/No), `Fluid_Density_Fact_Contents`, `Friction_Scale_Factor`, `Hot_Modulus_Case`, `Occasional_Load_Analysis_Type` | Analysis sets |
| `Support_Data_Listing` | `Point_Name`, `Support_Type` (Linestop, Guide-H, Guide-V, V-stop...), `Gap_1`, `Gap_2`, `Friction_Coefficient`, `Gap_Setting`, `Stiffness_Text` | Soportes (una fila por direccion) |
| `Anchor_Data_Listing` | `Point_Name` | Anclajes |
| `Press_Temp_Data_Listing` | `Point_Name`, `Pipe_ID`, `PT_Case`, `Pressure`, `Temperature`, `Expansion`, `Modulus`, `Yield_Stress` | P/T por punto y caso |
| `Pipe_Properties_Data_Listing` | `Pipe_Identifier`, `Actual_OD`, `Wall_Thickness`, `Pipe_Weight`, `Content_Weight`, `Pipe_Material` | Tuberias |
| `Coordinates_Data_Listing` | `Point_Name`, `Component_Type`, `Pipe_ID`, `Segment`, `X`, `Y`, `Z` | Geometria y longitudes |
| `Bend_Data_Listing` | `Point_Name`, `Radius`, `OD`, `Analysis_Set`, `Material` | Codos |
| `Nozzle_Data_Lisitng` (sic) | `Point_Name`, `Flexibility_Method`, `Vessel_Radius`, `Vessel_Thickness` | Toberas |
| `EQ_Load_Cases` | `Load_Case`, `X_Resultant`, `Y_Resultant`, `Z_Resultant` | Sismo estatico |
| `Unit_Info` | unidad de cada magnitud | Confirmar SI |

## Unidades (modelo en SI)
mm, N, N/m (pesos por metro), MPa para presion, N/mm2 para tensiones. `Modulus` viene en E6 N/mm2: MPa = valor x 1e6 (0,0007 = 700 MPa). `Expansion` en mm/m. La API, en cambio, habla pulgadas/psi/F.
