// Local browser development only; imported into a separate module for testing.
export function previewTransport() {
  let active = false;
  const ok = (data, status=200) => ({status, data:{data,error:null}});
  return async (path, method, body) => {
    if (path.endsWith('/auth/request')) return ok({challenge_id:'local-preview'},202);
    if (path.endsWith('/auth/verify')) {
      if (body.code !== '123456') return {status:401,data:{error:{message:'Preview code is 123456.'},data:null}};
      active=true;
      return ok({access_token:'preview-access',refresh_token:'preview-refresh',expires_in:900});
    }
    if (path.endsWith('/auth/logout')) { active=false; return ok({logged_out:true}); }
    if (!active) return {status:401,data:{error:{message:'Sign in again.'},data:null}};
    if (path.endsWith('/journey/status')) return ok({
      user:{user_id:'preview-user',display_name:'Preview profile',journey_state:'dating',bgv_status:'verified'},
      stage_indicator:{show:true,current:'dating',label:'Dating',stages:[
        {key:'dating',label:'Dating',state:'current'},{key:'relationship',label:'Relationship',state:'todo'},
        {key:'engaged',label:'Engaged',state:'todo'},{key:'married',label:'Married',state:'todo'}]},
      milestones:['registered','verified'],
      contact_verification:{required:true,satisfied:true,verified_email:false,verified_phone:true},
      clock:{mode:'simulation',week:1,day:'Mon',hour:12},
      current_lock_in:null,current_date_plan:null,current_couple:null,
      surfaces:[
        {key:'dashboard',eligible:true,blocked_reason:null,api_available:true,request:null},
        {key:'reach',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/reach'}},
        {key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}},
        {key:'guru',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/guidance'}},
        {key:'vision',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/profile/vision'}},
        {key:'chemistry',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/profile/chemistry'}},
        {key:'stats',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/profile/stats'}},
        {key:'verify',eligible:false,blocked_reason:'You are already verified.',api_available:false,request:null},
        {key:'relationship',eligible:false,blocked_reason:'This opens once you have both agreed to be exclusive.',api_available:false,request:null},
        {key:'journey',eligible:false,blocked_reason:'This opens once you have both agreed to be exclusive.',api_available:false,request:null},
      ],
      next_action:{headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.',cta:'See this week',
        destination:{key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}}},
    });
    if (path.endsWith('/profile')) return ok({stats:{age:30,city:'Bangalore',profession:'Engineering',diet:'Vegetarian'},visions:[{key:'Intimacy',stance:['Emotional']},{key:'Cohabitate',stance:['Chores split']} ]});
    if (path.endsWith('/reach')) return ok({counts:{mutual_open:3,fits_user_filters:12,no_realistic_matches:false}});
    if (path.endsWith('/week')) return ok({slots:[]});
    throw new Error('Unsupported preview request: '+path);
  };
}
