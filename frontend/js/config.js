/* 数据字典：授权角色/通道/设备、报告格式规则。
   纯数据，不含逻辑；新增授权方式或调整校验规则只改本文件。 */

const AUTH_CONFIG = {
  roles: [
    {key:"operator", title:"经办", name:"陈立", id:"NJ-AML-0231", post:"GW-AML-01", desc:"负责要素核对与初稿修订"},
    {key:"reviewer", title:"复核", name:"张敏", id:"NJ-AML-0108", post:"GW-AML-02", desc:"负责要素完整性、定性是否成立"},
    {key:"approver", title:"审批", name:"王建国", id:"NJ-CC-0006", post:"GW-CC-01", desc:"负责报送合规性终审与责任签发"}
  ],
  channels: [
    {key:"branch", name:"网点柜面", methods:["指纹识别","授权卡","刷员工卡"]},
    {key:"mobile", name:"移动端", methods:["人脸识别","指纹识别","通行密钥"]},
    {key:"oa", name:"OA 通行密钥", methods:["通行密钥","授权卡"]}
  ],
  devices: {
    branch:{指纹识别:{device:"FP-NJ-0231",score:"98.6%"}},
    mobile:{指纹识别:{device:"MOB-FP-01",score:"97.9%"},
            人脸识别:{device:"MOB-CAM-01",score:"97.2%"}}
  }
};

const REPORT_CONFIG = {
  totalItems: 62,
  partCount: 4,
  longTextLength: 40,
  longTextItems: [21,22,46,61],
  requiredItems: [1,24],
  dateItems: [21,29,30,38],
  amountItem: 48,
  idItem: 6,
  orgItem: 1,
  orgCodeLength: 15,
  idPattern: "^\\d{15}$|^\\d{17}[\\dXx]$"
};
