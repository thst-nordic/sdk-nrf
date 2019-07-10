
@Library("CI_LIB@lib_master") _

def IMAGE_TAG = lib_Main.getDockerImage(JOB_NAME)
def AGENT_LABELS = lib_Main.getAgentLabels(JOB_NAME)

def REPO_CI_TOOLS = "https://github.com/zephyrproject-rtos/ci-tools.git"
def REPO_CI_TOOLS_SHA = "bfe635f102271a4ad71c1a14824f9d5e64734e57"
def CI_STATE = new HashMap()

pipeline {

  parameters {
       booleanParam(name: 'RUN_DOWNSTREAM', description: 'if false skip downstream jobs', defaultValue: true)
       booleanParam(name: 'RUN_TESTS', description: 'if false skip testing', defaultValue: true)
       booleanParam(name: 'RUN_BUILD', description: 'if false skip building', defaultValue: false)
       string(name: 'jsonstr_CI_STATE', description: 'Default State if no upstream job',
              defaultValue: '''{
"NRFXLIB":{"WAITING":"false", "BRANCH_NAME":"master","GIT_BRANCH":" ","GIT_URL":"https://github.com/NordicPlayground/nrfxlib.git"},
"ZEPHYR":{"WAITING":"false", "BRANCH_NAME":"master","GIT_BRANCH":" ","GIT_URL":"https://github.com/NordicPlayground/fw-nrfconnect-zephyr.git"},
"MCUBOOT":{"WAITING":"false", "BRANCH_NAME":"master","GIT_BRANCH":" ","GIT_URL":"https://github.com/NordicPlayground/fw-nrfconnect-mcuboot.git"}
}''')
              // defaultValue: '''{"NRFX":{"WAITING":"false","GIT_BRANCH":" ","GIT_URL":"https://projecttools.nordicsemi.no/bitbucket/scm/nrffosdk/nrfx.git","BRANCH_NAME":"master"},"jobStack":["ZEPHYR"],"ZEPHYR":{"RUN_BUILD":"false","RUN_DISPLAY_URL":"https://jenkins-ncs.nordicsemi.no/job/thst/job/thst_fw-nrfconnect-zephyr/job/lib_test/60/display/redirect","HUDSON_HOME":"/var/lib/jenkins","RUN_CHANGES_DISPLAY_URL":"https://jenkins-ncs.nordicsemi.no/job/thst/job/thst_fw-nrfconnect-zephyr/job/lib_test/60/display/redirect?page=changes","JOB_URL":"https://jenkins-ncs.nordicsemi.no/job/thst/job/thst_fw-nrfconnect-zephyr/job/lib_test/","library.CI_LIB.version":"lib_master","RUN_DOWNSTREAM":"true","BUILD_ID":"60","JOB_NAME":"thst/thst_fw-nrfconnect-zephyr/lib_test","HUDSON_URL":"https://jenkins-ncs.nordicsemi.no/","JENKINS_SERVER_COOKIE":"eb976e612098d3da","REPORT_SHA":"fcf35f63e96a8168d86c7be46b9438cecd3e34a3","JENKINS_URL":"https://jenkins-ncs.nordicsemi.no/","RUN_TESTS":"true","GIT_COMMIT":"fcf35f63e96a8168d86c7be46b9438cecd3e34a3","BUILD_TAG":"jenkins-thst-thst_fw-nrfconnect-zephyr-lib_test-60","manifest":[{"sha":"fcf35f63e96a8168d86c7be46b9438cecd3e34a3","repoName":"zephyr","url":"https://github.com/thst-nordic/fw-nrfconnect-zephyr.git"}],"HUDSON_SERVER_COOKIE":"eb976e612098d3da","BUILD_TYPE":"BRANCH","JOB_BASE_NAME":"lib_test","CLASSPATH":"","JENKINS_HOME":"/var/lib/jenkins","jsonstr_CI_STATE":"{"NRFX":{"WAITING":"false", "BRANCH_NAME":"master","GIT_BRANCH":" ","GIT_URL":"https://projecttools.nordicsemi.no/bitbucket/scm/nrffosdk/nrfx.git"},}","BUILD_NUMBER":"60","BUILD_DISPLAY_NAME":"#60","BUILD_URL":"https://jenkins-ncs.nordicsemi.no/job/thst/job/thst_fw-nrfconnect-zephyr/job/lib_test/60/","JOB_DISPLAY_URL":"https://jenkins-ncs.nordicsemi.no/job/thst/job/thst_fw-nrfconnect-zephyr/job/lib_test/display/redirect","WAITING":true,"GIT_BRANCH":"lib_test","GIT_URL":"https://github.com/thst-nordic/fw-nrfconnect-zephyr.git","BRANCH_NAME":"lib_test"},"ENV":"THST"}''')
  }

  agent {
    docker {
      image "$IMAGE_TAG"
      label "$AGENT_LABELS"
      args '-e PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/workdir/.local/bin'
    }
  }

  options {
    checkoutToSubdirectory('nrf')
  }

  triggers {
    cron(env.BRANCH_NAME == 'master' ? '0 */4 * * 1-7' : '') // Only master will be build periodically
  }

  environment {
      // ENVs for check-compliance
      GH_TOKEN = credentials('nordicbuilder-compliance-token') // This token is used to by check_compliance to comment on PRs and use checks
      GH_USERNAME = "NordicBuilder"
      COMPLIANCE_ARGS = "-r NordicPlayground/fw-nrfconnect-nrf"

      // Build all custom samples that match the ci_build tag
      SANITYCHECK_OPTIONS = "--board-root $WORKSPACE/nrf/boards --testcase-root $WORKSPACE/nrf/samples --testcase-root $WORKSPACE/nrf/applications --build-only --disable-unrecognized-section-test -t ci_build --inline-logs"
      ARCH = "-a arm"
      LC_ALL = "C.UTF-8"

      // ENVs for building (triggered by sanitycheck)
      ZEPHYR_TOOLCHAIN_VARIANT = 'gnuarmemb'
      GNUARMEMB_TOOLCHAIN_PATH = '/workdir/gcc-arm-none-eabi-7-2018-q2-update'
  }

  stages {
    stage('Load') {
      steps {
        script {
          lib_State.preLoad()
          CI_STATE = lib_State.load(params['jsonstr_CI_STATE'])
          lib_State.store('NRF', CI_STATE)
          lib_State.getParentJob(CI_STATE)
          lib_State.pushjobStack('NRF', CI_STATE)
          println "CI_STATE = $CI_STATE"
        }
      }
    }
    stage('Checkout repositories') {
      when { expression { CI_STATE.NRF.RUN_TESTS || CI_STATE.NRF.RUN_BUILD } }
      steps {
        script {
          lib_Main.cloneCItools(JOB_NAME)
          CI_STATE.NRF.REPORT_SHA = lib_Main.checkoutRepo(CI_STATE.NRF.GIT_URL, "nrf", CI_STATE, false)
          lib_West.InitUpdate('nrf')
        }
      }
    }
    stage('Apply Parent Manifest Updates') {
      when { expression { CI_STATE.NRF.RUN_TESTS || CI_STATE.NRF.RUN_BUILD } }
      steps {
        script {
          println "If triggered by an upstream Project, use their changes."
          lib_West.ApplyManfestUpdates(CI_STATE)
        }
      }
    }
    stage('Run compliance check') {
      when { expression { CI_STATE.NRF.RUN_TESTS } }
      steps {
        dir('nrf') {
          script {
            // If we're a pull request, compare the target branch against the current HEAD (the PR), and also report issues to the PR
            def BUILD_TYPE = lib_Main.getBuildType(CI_STATE.NRF)
            if (BUILD_TYPE == "PR") {
              COMMIT_RANGE = "$CI_STATE.NRF.MERGE_BASE..$CI_STATE.NRF.REPORT_SHA"
              COMPLIANCE_ARGS = "$COMPLIANCE_ARGS -p $CHANGE_ID -S $CI_STATE.NRF.REPORT_SHA -g"
              println "Building a PR [$CHANGE_ID]: $COMMIT_RANGE"
            }
            else if (BUILD_TYPE == "TAG") {
              COMMIT_RANGE = "tags/${env.BRANCH_NAME}..tags/${env.BRANCH_NAME}"
              println "Building a Tag: " + COMMIT_RANGE
            }
            // If not a PR, it's a non-PR-branch or master build. Compare against the origin.
            else if (BUILD_TYPE == "BRANCH") {
              COMMIT_RANGE = "origin/${env.BRANCH_NAME}..HEAD"
              println "Building a Branch: " + COMMIT_RANGE
            }
            else {
                assert condition : "Build fails because it is not a PR/Tag/Branch"
            }

            // Run the compliance check
            try {
              sh "(source ../zephyr/zephyr-env.sh && ../ci-tools/scripts/check_compliance.py $COMPLIANCE_ARGS --commits $COMMIT_RANGE)"
            }
            finally {
              junit 'compliance.xml'
              archiveArtifacts artifacts: 'compliance.xml'
            }
          }
        }
      }
    }
    stage('Build samples') {
      when { expression { CI_STATE.NRF.RUN_BUILD } }
      steps {
        // Create a folder to store artifacts in
        sh 'mkdir artifacts'

        // Build all the samples
        dir('zephyr') {
          sh "source zephyr-env.sh && ./scripts/sanitycheck $SANITYCHECK_OPTIONS"
        }

        script {
          /* Rename the nrf52 desktop samples */
          desktop_platforms = ['nrf52840_pca20041', 'nrf52_pca20037', 'nrf52840_pca10059']
          for(int i=0; i<desktop_platforms.size(); i++) {
            file_path = "zephyr/sanity-out/${desktop_platforms[i]}/nrf_desktop/test/zephyr/zephyr.hex"
            check_and_store_sample("$file_path", "nrf_desktop_${desktop_platforms[i]}.hex")
            file_path = "zephyr/sanity-out/${desktop_platforms[i]}/nrf_desktop/test_zrelease/zephyr/zephyr.hex"
            check_and_store_sample("$file_path", "nrf_desktop_${desktop_platforms[i]}_ZRelease.hex")
          }

          /* Rename the nrf9160 samples */
          samples = ['spm']
          for(int i=0; i<samples.size(); i++)
          {
            file_path = "zephyr/sanity-out/nrf9160_pca10090/nrf9160/${samples[i]}/test_build/zephyr/zephyr.hex"
            check_and_store_sample("$file_path", "${samples[i]}_nrf9160_pca10090.hex")
          }
          ns_samples = ['lte_ble_gateway', 'at_client']
          for(int i=0; i<ns_samples.size(); i++)
          {
            file_path = "zephyr/sanity-out/nrf9160_pca10090ns/nrf9160/${ns_samples[i]}/test_build/zephyr/zephyr.hex"
            check_and_store_sample("$file_path", "${ns_samples[i]}_nrf9160_pca10090ns.hex")
          }
          ns_apps = ['asset_tracker']
          for(int i=0; i<ns_apps.size(); i++)
          {
            file_path = "zephyr/sanity-out/nrf9160_pca10090ns/${ns_apps[i]}/test_build/zephyr/zephyr.hex"
            check_and_store_sample("$file_path", "${ns_apps[i]}_nrf9160_pca10090ns.hex")
          }
        }
        archiveArtifacts allowEmptyArchive: true, artifacts: 'artifacts/*.hex'
      }
    }
    stage('Trigger testing build') {
      when { expression { CI_STATE.NRF.RUN_DOWNSTREAM } }
      steps {
        script {
          CI_STATE.NRF.WAITING = true
          def jsonstr_CI_STATE = lib_Util.HashMap2Str(CI_STATE)
          println "jsonstr_CI_STATE = " + jsonstr_CI_STATE
          def DOWNSTREAM_JOBS = lib_Main.getDownStreamJobs(CI_STATE, 'NRF')
          println "DOWNSTREAM_JOBS = " + DOWNSTREAM_JOBS
          // lib_West.AddManifestUpdate("NRF", 'nrf', CI_STATE.NRF.GIT_URL, CI_STATE.NRF.REPORT_SHA, CI_STATE)
          def jobs = [:]
          DOWNSTREAM_JOBS.each {
            jobs["${it}"] = {
              build job: "${it}", propagate: true, wait: true, parameters: [
                        string(name: 'jsonstr_CI_STATE', value: lib_Util.HashMap2Str(CI_STATE))]
            }
          }
          parallel jobs
        }
      }
    }
  }
  post {
    // This is the order that the methods are run. {always->success/abort/failure/unstable->cleanup}
    always {
      echo "always"
    }
    success {
      echo "success"
    }
    aborted {
      echo "aborted"
    }
    unstable {
      echo "unstable"
    }
    failure {
      echo "failure"
    }
    cleanup {
        echo "cleanup"
        cleanWs()
    }
  }
}



/**
  * Copy files to artifacts dir if they exist
  * 
  * @param path path
  * @param new_name new_name
  * 
  */
def check_and_store_sample(path, new_name) {
  script {
    if (fileExists(file_path)) {
      sh "cp ${path} artifacts/${new_name}"
    }
    else {
      echo "Build for ${new_name} failed"
      currentBuild.result = 'FAILURE'
    }
  }
}