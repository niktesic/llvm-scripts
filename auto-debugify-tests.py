#!/usr/bin/python

import sys
import argparse
import os
import subprocess
import json

# Argumenti komandne linije.
def parse_program_args(parser):
  parser.add_argument("-process-tests", action="store",
            default="",
            dest="tests_dir",
            help="process tests from a given directory"
            )
  parser.add_argument("-use-lit", action="store",
            default="~/compiler/build_dev/bin/llvm-lit",
            dest="lit_path",
            help="specify llvm-lit path"
            )
  parser.add_argument("-report-file", action="store",
            default="./report_test.json",
            dest="report_file",
            help="store bug report in file as a JSON"
            )
  parser.add_argument("-opt-arg", action="store",
            default="",
            dest="opt_arg",
            help="specify optimization pass arg"
            )
  # Novi argument za odabir rezima rada.
  parser.add_argument("-mode", action="store",
            default="synthetic",
            dest="mode",
            help="specify debugify mode (synthetic or original)"
            )
  return parser.parse_args()

# Provera vrednosti argumenata komandne linije.
def check_args(results):
  if len(sys.argv) < 2:
    print ("error: No test directory specified.")
    return False
  elif results.tests_dir != "" and os.path.isdir(results.tests_dir) == False:
    print ("error: Please specify a directory where the tests are stored.")
    return False
  elif results.lit_path != "" and os.path.isfile(results.lit_path) == False:
    print ("error: Please specify a valid llvm-lit binary path.")
    return False
  elif results.mode != "synthetic" and results.mode != "original":
    print ("error: Please specify a valid debugify mode (synthetic or original).")
    return False

  return True

# Pretraga svih C i IR testova.
def searchTests(path):
  files = []
  for r, d, f in os.walk(path):
    for file in f:
      if file.endswith(".c") or file.endswith(".ll"):
        if "Inputs" in os.path.join(r,file):
          continue
        files.append(os.path.join(r, file))

  return files

# Parsiranje test direktorijuma iz pune putanje testa.
def getTestPath(test_file,type):
  if type != "short" and type != "dir":
    print ("error: Please specify test dir path as full or short.")
    sys.exit(1)
  arr  = test_file.split("/")
  dir = ""
  short = ""
  for w in arr:
    if ".c" not in w and ".ll" not in w:
      dir = dir + w + "/"
    if w == "test":
      short = ""
    else:
      short = short + "/" + w
    
  if type == "short":
    return short
  
  return dir

# Cuvanje stare lokalne lit konfiguracije i postavljanje nove.
def changeLitLocalConfig(test_file):
  test_dir = getTestPath(test_file,"dir")
  cfg_file_path = test_dir + "lit.local.cfg"
  # Preskakanje test direktorijuma bez lokalne konfiguracije.
  if not os.path.exists(cfg_file_path):
    return

  # Cuvanje stare konfiguracije.
  fin = open(cfg_file_path,"rt")
  data_old = fin.read()
  fin.close()
  # Izmena lokalne lit konfiguracije.
  f = open(cfg_file_path,"r")
  lines = f.readlines()
  outstr = ""
  for l in lines:
    a = l
    # Brisanje nezeljenog -g argumenta kompajlera.
    if "-g" in l:
      a = l.replace("-g","")
    outstr = outstr + a
  f.close()
  # Upis nove lit konfiguracije.
  fout = open(cfg_file_path,"wt")
  fout.write(outstr)
  fout.close()
  
  return data_old

# Restauracija originalne lokalne lit konfiguracije.
def retrieveLitLocalConfig(test_file,data_old):
  test_dir = getTestPath(test_file,"dir")
  cfg_file_path = test_dir + "lit.local.cfg"
  # Preskakanje test direktorijuma bez lokalne konfiguracije.
  if not os.path.exists(cfg_file_path):
    return

  fout = open(cfg_file_path,"wt")
  fout.write(data_old)
  fout.close()

# Mapiranje samo neophodnih (podrzanih) argumenata clang kompajlera iz testa.
def mapArg(arg):
  a = ""
  # Argumenti nespecificni za prolaz.
  if "target" in arg:
    a = arg
  # Slucaj makroa -D MACRO.
  elif "-D" == arg:
    a = "-D"
  # Slucaj makroa -DMACRO.
  elif "-D" in arg:
    a = arg

  return a

# Modifikacija argumenata clang-RUN linije i preusmerenje izlaza
# ka opt komandi sa ukljucenim debugify-em.
def modifyClangArgs(args, mode):
  mod = ""
  # U slucaju originalnog rezima, generisati informacije za debagovanje.
  if mode == "original":
    mod += " -g"
  output = False
  arg_list = args.split(" ")
  new_arg = ""
  for a in arg_list:
    # Eliminacija karaktera za novi red.
    if "\n" in a:
      a = a.rstrip("\n")
    # Eliminacija starih preusmerenja clang komande.
    if ">" in a or "|" in a:
      break
    # Eliminacija starog argumenta za izlaznu datoteku.
    if output and "%t" in a:
      output = False
      continue
    if a == "-o":
      output = True
      continue
    # Ocuvanje definisanih makroa.
    if new_arg == "-D":
      new_arg = a
    # Mapiranje ostalih argumenata clang kompajlera.
    else:
      new_arg = mapArg(a)
    # Dodavanje azuriranog argumenta u listu.
    mod = mod + " " + new_arg

  # Dodavanje "-S -emit-llvm" argumentima clang-a.
  mod = mod + " -emit-llvm"
  # Dodavanje "-Xclang -disable-llvm-passes" argumentima clang-a.
  mod = mod + " -Xclang -disable-llvm-passes"
  # Prosledjivanje izlaza clang-a ka opt-u sa ukljucenim debugify-em,
  # u zavisnosti od ukljucenog rezima.
  if mode == "original":
    mod = mod + " -c %s -o - | opt -O3 -verify-each-debuginfo-preserve -disable-output"
  else:
    mod = mod + " -c %s -o - | opt -O3 -debugify-each -disable-output"

  return mod

# Sastavljanje modifikovane RUN linije testa.
def modifyRunClang(line, mode):
  modified = line
  linearr = line.split("clang")
  beg = linearr[0]
  after = linearr[1]
  cmd = after.split(";",1)
  args = cmd[0]
  # Postavka clang-opt poziva sa argumentima
  mod_args = modifyClangArgs(args, mode)
  modified = beg + "clang" + mod_args
  if "not clang" in modified:
    modified = modified.replace("not clang","clang")
  return modified

# Kreiranje izvestaja za jedan gubitak debag lokacije koji
# je detektovao debugify.
def getBugReport(line):
  action = ""
  bb_name = "unknown"
  fn_name = ""
  instr = ""
  metadata = ""
  # Postavljanje vrednosti polja JSON objekta.
  # Sinteticki rezim.
  if "Instruction with empty DebugLoc in function" in line:
    # Format: Instruction with empty DebugLoc in function #fn-name# --  #instr#
    action = "drop"
    arr = line.split(" ")
    fn_name = arr[7]
    instr = line.split("--  ")[1]
    instr = instr.split("\n")[0]
    metadata = "DILocation"
  # Originalni rezim.
  if "DILocation" in line:
    # Format: Instruction with empty DebugLoc in function #fn-name# --  #instr#
    # #pass# dropped DILocation of  #instr# (BB: #bb-name#, Fn: #fn-name#, File: modified test)
    # #pass# did not generate DILocation for  #instr# (BB: #bb-name#, Fn: #fn-name#, File: modified test)
    # at the end of the pass #pass#: FAIL
    if "dropped" in line:
      action = "drop"
      instr = line.split("of  ")[1]
      instr = instr.split(" (")[0]
    elif "did not generate" in line:
      action = "not-generate"
      instr = line.split("for  ")[1]
      instr = instr.split(" (")[0]
    else:
      return {"action": ""}
    if "Fn: " in line:
      fn_name = line.split("Fn: ")[1]
      fn_name = fn_name.split(", ")[0]
    if "BB: " in line:
      bb_name = line.split("BB: ")[1]
      bb_name = bb_name.split(", ")[0]
    metadata = "DILocation"

  # Formira izvestaj o jednom bag-u - WARNING: liniji.
  py_obj = {"action": action,"bb-name":bb_name,"fn-name":fn_name,"instr":instr,"metadata":metadata}
  return py_obj

# Parsiranje izlaza debugify-a.
def parseDebugifyOutput(output_file,test_file):
  fail = False
  cur_pass = ""
  bugs = []
  ret = []
  
  # Dohvatanje skracene putanje testa.
  short_test_path = getTestPath(test_file,"short")

  f = open(output_file,"r")
  lines = f.readlines()  
  for line in lines:
    if "Skipping" in line:
      continue
    # Kompletiranje izvestaja za jedan optimizacioni prolaz.
    # Sinteticki rezim.
    if "CheckModuleDebugify" in line or "CheckFunctionDebugify" in line:
      cur_pass = line.split("[")[1].split("]")[0]
      if bugs:
        # Sastavljanje JSON objekta za dati prolaz.
        ret_obj = {"file":short_test_path, "pass":cur_pass, "bugs": [bugs]}
        ret_json = json.dumps(ret_obj)
        ret.append(ret_json)
        bugs = []
    # Originalni rezim.
    if "FAIL" in line:
      cur_pass = line.split(":")[0]
      if bugs:
        # Sastavljanje JSON objekta za dati prolaz.
        ret_obj = {"file":short_test_path, "pass":cur_pass, "bugs": [bugs]}
        ret_json = json.dumps(ret_obj)
        ret.append(ret_json)
        bugs = []
    # Parsiranje WARNING linije.
    if "WARNING" in line:
      report = getBugReport(line)
      if report["action"] != "":
        bugs.append(report)

  f.close()

  return ret

# Kreiranje novog testa na osnovu starog C testa.
def createModifiedCTest(old_test, new_test, tmp_output, pass_arg, mode):
  lines = old_test.readlines()
  it = 0
  for line in lines:
    if "RUN:" in line:
      if "clang" in line:
        # Prosledjuje izlaz modifikovane clang komande u privremenu
        # datoteku za prikupljanje izlaznih podataka.
        mod_line = modifyRunClang(line, mode)
        mod_line += " " + pass_arg
        new_test.write(mod_line)
        if "clang" in mod_line:
          it = it + 1
          new_test.write(" >& "+tmp_output + str(it))
        new_test.write("\n")
      elif "FileCheck" in line:
        continue
      elif "RUN: %t" in line:
        continue
      elif "RUN: test" in line:
        continue
      elif "-s %t" in line:
        continue
      elif "diff" in line:
        continue
      else:
        new_test.write(line)
    else:
      new_test.write(line)

  return it

# Kreiranje novog testa na osnovu starog IR testa.
def createModifiedLLTest(old_test, new_test, tmp_output, pass_arg, mode):
  lines = old_test.readlines()
  for line in lines:
    # Izostavljanje starih RUN linija.
    if "RUN:" in line:
      continue
    else:
      new_test.write(line)
  # Ubacivanje zeljene RUN linije za debugify analizu, u zavisnosti od rezima.
  run_opt = "; RUN: opt %s -O3 -debugify-each -disable-output " + pass_arg
  if mode == "original":
    run_opt = "; RUN: opt %s -debugify -O3 -enable-new-pm=false -verify-each-debuginfo-preserve -disable-output " + pass_arg
  new_test.write(run_opt)
  new_test.write(" >& "+tmp_output + str(1))

  return 1

# Modifikacija testa tako da koristi -debugify-each i pokretanje istog
# pomocu llvm-lit alata.
def processTest(test_file,lit_path,report_file,pass_arg, mode):
  print ("Processing test: "+ test_file)
  # Provera da li originalni test postoji.
  if not os.path.isfile(test_file):
    print ("File path {} does not exist. Exiting...".format(filepath))
    sys.exit()

  # Otvaranje originalnog testa.
  file = open(test_file,"r")
  
  # Kreiranje privremene test datoteke za cuvanje modifikovanog testa.
  tmp_test = getTestPath(test_file,"dir")+"modified_test.c"
  if test_file.endswith(".ll"):
    tmp_test = getTestPath(test_file,"dir")+"modified_test.ll"
  # Kreiranje privremene datoteke za prikupljanje izlaznih podataka debugify analize.
  f = open(tmp_test,"w")
  tmp_output = getTestPath(test_file,"dir")+"test_output.tmp"

  try:
    try:
      # Kreiranje modifikovanog testa.
      if test_file.endswith(".c"):
        it = createModifiedCTest(file, f, tmp_output, pass_arg, mode)
      elif test_file.endswith(".ll"):
        it = createModifiedLLTest(file, f, tmp_output, pass_arg, mode)
    finally:
      file.close()
      f.close()
  except:
    # Brisanje modifikovanog testa u slucaju greske.
    os.remove(tmp_test)
    

  try:
    # Izmena (prilagodjavanje) lokalne lit konfiguracije.
    old_config = changeLitLocalConfig(test_file)
    # Pokretanje modifikovanog testa.
    lit_cmd = lit_path + " -a " + tmp_test + " &> /dev/null"
    process = subprocess.Popen(lit_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Cekanje na zavrsetak procesa testiranja.
    out, err = process.communicate()
    retVal = process.returncode

    # Prikuplljanje izvestaja svih izvrsenih debugify analiza u jednu 
    # datoteku.
    report_output = open(report_file,"a")
    i = 0
    while (i<it):
      i = i + 1
      # Ispis poruke o neprocesiranom testu.
      if retVal != 0:
        print ("DEBUGIFY-EACH - NOT PROCESSED\n")
        continue
      if not os.path.exists(tmp_output+str(i)):
        print ("Test output file " + tmp_output+str(i) + " is not created.")
        print ("Probably one of the previous commands failed!")
        continue
      # Prikupljanje debugify izvestaja o bagovima.
      pass_reports = parseDebugifyOutput(tmp_output+str(i),test_file)
      # Ispis poruke o procesiranom testu (uspesno ili neuspesno).
      if not pass_reports:
        print ("DEBUGIFY-EACH - PASS\n")
      else:
        print ("DEBUGIFY-EACH - FAIL\n")
        # Upis izvestaja u datoteku sa svim prikupljenim izvestajima.
        for r in pass_reports:
          report_output.write(r)
          report_output.write("\n")

  finally:
    # Brisanje modifikovanog testa u svakom slucaju.
    os.remove(tmp_test)
    # Brisanje svih privremenih datoteka za prikupljanje izvestaja.
    for j in range(1,it+1):
      if os.path.exists(tmp_output+str(j)):
        os.remove(tmp_output+str(j))
    # Vracanje originalne lokalne lit konfiguracije.
    retrieveLitLocalConfig(test_file,old_config)
    report_output.close()
  
  if retVal == 0:
    return True
  else:
    return False

# Glavna procedura.
def Main():
  print ("== debugify tests ==")
  print ("")
  print ("")

  # Parsiranje i provera argumenata poziva skripte.
  parser = argparse.ArgumentParser()
  results = parse_program_args(parser)
  if check_args(results) == False:
    print ("error: Invalid input\n")
    parser.print_help()
    sys.exit(1)
  
  # Kreiranje datoteke za belezenje izvestaja u JSON formatu.
  report_file = results.report_file
  if os.path.exists(report_file):
    os.remove(report_file)
  
  # Pretraga svih testova od interesa.
  td_abs_path = os.path.abspath(results.tests_dir)
  tests = searchTests(td_abs_path)
  skipped = 0
  # Procesiranje svakog dostupnog testa.
  for t in tests:
    if not processTest(t,results.lit_path,report_file,results.opt_arg,results.mode):
      skipped += 1

  # Ispis poruke o obradjenim testovima.
  print ("===== Processed tests ======")
  print ("Total number of tests: " + str(len(tests)))
  print ("Number of skipped tests: " + str(skipped))

if __name__ == "__main__":
  Main()